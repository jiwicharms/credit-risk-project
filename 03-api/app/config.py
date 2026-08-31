from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    aws_region: str = "us-east-1"

    redshift_workgroup: Optional[str] = None
    redshift_cluster_id: Optional[str] = None
    redshift_db_user: Optional[str] = None
    redshift_database: str = "dev"
    redshift_schema: str = "credit_risk_prod"
    ml_predict_function: str = "predict_credit_growth"

    forecast_table: str = "latest_forecast"
    query_timeout_seconds: float = 30.0
    forecast_cache_seconds: int = 900  # 15 min; FRED updates monthly

    def target(self) -> dict:
        if self.redshift_workgroup:
            return {"WorkgroupName": self.redshift_workgroup}
        if self.redshift_cluster_id:
            return {
                "ClusterIdentifier": self.redshift_cluster_id,
                "DbUser": self.redshift_db_user or "awsuser",
            }
        raise RuntimeError(
            "Set REDSHIFT_WORKGROUP (Serverless) or REDSHIFT_CLUSTER_ID (provisioned)."
        )


settings = Settings()
