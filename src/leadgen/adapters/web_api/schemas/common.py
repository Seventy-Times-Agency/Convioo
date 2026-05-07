"""Shared / common schemas used across multiple domains."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    db: bool
    commit: str
