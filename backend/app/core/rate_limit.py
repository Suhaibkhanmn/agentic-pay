"""
Rate limiter — per-user when authenticated, per-IP as fallback.

Reads X-Forwarded-For / X-Real-IP so it works behind Vercel/Render/nginx
proxies instead of always seeing 127.0.0.1.
"""

from starlette.requests import Request
from slowapi import Limiter


def _get_real_ip(request: Request) -> str:
    """Extract client IP from proxy headers, falling back to direct IP."""
    # X-Forwarded-For: client, proxy1, proxy2 — first entry is the real client
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _rate_limit_key(request: Request) -> str:
    """
    Per-user key when authenticated (fair, not gameable by IP rotation).
    Falls back to IP for unauthenticated endpoints (login, register).
    """
    # The auth dependency injects user info before the rate limiter runs,
    # but the token is in the header — we can extract the subject cheaply.
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from jose import jwt
            from app.core.config import settings

            token = auth_header.split(" ", 1)[1]
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass  # fall through to IP-based

    return _get_real_ip(request)


limiter = Limiter(key_func=_rate_limit_key)
