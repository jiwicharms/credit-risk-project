

from __future__ import annotations

import logging
import time
from typing import Any, Mapping, Sequence

import boto3
from botocore.config import Config as BotoConfig

from .config import settings

log = logging.getLogger(__name__)

_TERMINAL_OK = "FINISHED"
_TERMINAL_BAD = ("FAILED", "ABORTED")


class RedshiftQueryError(RuntimeError):
    """Raised when a statement fails, is aborted, or exceeds the timeout."""


def _unwrap(cell: Mapping[str, Any]) -> Any:
    if cell.get("isNull"):
        return None
    return next(iter(cell.values()))


class RedshiftDataClient:
    def __init__(self) -> None:
        self._client = boto3.client(
            "redshift-data",
            region_name=settings.aws_region,
            config=BotoConfig(retries={"max_attempts": 3, "mode": "standard"}),
        )

    def run(
        self,
        sql: str,
        params: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        timeout = timeout or settings.query_timeout_seconds

        kwargs: dict[str, Any] = {
            "Database": settings.redshift_database,
            "Sql": sql,
            **settings.target(),
        }
        if params:
            kwargs["Parameters"] = [
                {"name": k, "value": str(v)} for k, v in params.items()
            ]

        started = time.monotonic()
        statement_id = self._client.execute_statement(**kwargs)["Id"]

        delay = 0.15
        while True:
            described = self._client.describe_statement(Id=statement_id)
            status = described["Status"]

            if status == _TERMINAL_OK:
                break
            if status in _TERMINAL_BAD:
                raise RedshiftQueryError(
                    f"statement {statement_id} {status}: "
                    f"{described.get('Error', 'no error detail')}"
                )
            if time.monotonic() - started > timeout:
                self._client.cancel_statement(Id=statement_id)
                raise RedshiftQueryError(
                    f"statement {statement_id} exceeded {timeout:.1f}s"
                )

            time.sleep(delay)
            delay = min(delay * 1.5, 1.0)

        log.info(
            "redshift statement %s finished in %.0fms",
            statement_id,
            (time.monotonic() - started) * 1000,
        )

        if not described.get("HasResultSet"):
            return []
        return self._fetch(statement_id)

    def _fetch(self, statement_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        columns: Sequence[str] | None = None
        next_token: str | None = None

        while True:
            page_kwargs: dict[str, Any] = {"Id": statement_id}
            if next_token:
                page_kwargs["NextToken"] = next_token
            page = self._client.get_statement_result(**page_kwargs)

            if columns is None:
                columns = [c["name"] for c in page["ColumnMetadata"]]

            for record in page["Records"]:
                rows.append({c: _unwrap(v) for c, v in zip(columns, record)})

            next_token = page.get("NextToken")
            if not next_token:
                return rows

    def ping(self) -> bool:
        return self.run("SELECT 1 AS ok", timeout=10.0)[0]["ok"] == 1


client = RedshiftDataClient()
