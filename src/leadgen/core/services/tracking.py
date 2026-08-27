"""HMAC token helpers for email open tracking pixels."""

from __future__ import annotations

import base64
import hashlib
import hmac

from leadgen.config import get_settings


def generate_track_token(lead_id: str, user_id: str) -> str:
    msg = f"{lead_id}:{user_id}".encode()
    key = get_settings().auth_jwt_secret.encode()
    sig = hmac.new(key, msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")[:32]


def verify_track_token(token: str, lead_id: str, user_id: str) -> bool:
    return hmac.compare_digest(token, generate_track_token(lead_id, user_id))
