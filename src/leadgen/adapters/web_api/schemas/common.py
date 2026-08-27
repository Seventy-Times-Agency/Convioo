"""Shared / common schemas used across multiple domains."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    db: bool
    commit: str
    # Optional dependency probes. ``None`` means "not configured / not
    # checked"; ``True`` / ``False`` mean the probe ran and gave a
    # verdict. Used by Railway alerts and the /app/admin overview.
    redis: bool | None = None
    queue_depth: int | None = None
