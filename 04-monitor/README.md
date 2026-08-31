# Monitoring: Prometheus + Grafana

Scrapes `/metrics` on the deployed Elastic Beanstalk environment directly
over the public internet -- no VPC access or tunnel needed, since `/metrics`
is a normal HTTP endpoint on the same public CNAME as everything else.

## Run

```bash
cd 04-monitor
docker compose up -d
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

The dashboard is provisioned automatically -- open Grafana, it is already
there under "Credit risk API (prod)".