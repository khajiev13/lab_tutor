from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RootResponse(BaseModel):
    message: str


HealthCheckStatus = Literal["ok", "error", "skipped"]
OverallHealthStatus = Literal["healthy", "degraded", "unhealthy"]


class HealthCheckItem(BaseModel):
    name: str
    status: HealthCheckStatus
    detail: str | None = None


class HealthResponse(BaseModel):
    status: OverallHealthStatus
    checks: list[HealthCheckItem]
