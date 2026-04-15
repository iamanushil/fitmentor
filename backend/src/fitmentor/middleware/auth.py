"""Clerk JWT verification with Redis-cached JWKS."""
import json
import logging
from typing import Any

import httpx
import redis.asyncio as aioredis
from jose import JWTError, jwt

from fitmentor.config import get_settings

log = logging.getLogger(__name__)

_JWKS_CACHE_KEY = "clerk:jwks"
_JWKS_TTL_SECONDS = 86_400  # 24 hours

_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def _fetch_jwks() -> dict[str, Any]:
    """Fetch JWKS from Clerk and return the raw dict."""
    settings = get_settings()
    if not settings.clerk_jwks_url:
        raise RuntimeError("CLERK_JWKS_URL not configured")

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(settings.clerk_jwks_url)
        response.raise_for_status()
        return response.json()


async def get_jwks() -> dict[str, Any]:
    """Return JWKS, serving from Redis cache when available."""
    redis = _get_redis()

    cached = await redis.get(_JWKS_CACHE_KEY)
    if cached:
        return json.loads(cached)

    jwks = await _fetch_jwks()
    await redis.setex(_JWKS_CACHE_KEY, _JWKS_TTL_SECONDS, json.dumps(jwks))
    log.info("clerk.jwks.refreshed")
    return jwks


async def verify_clerk_token(token: str) -> dict[str, Any]:
    """
    Verify a Clerk-issued JWT (RS256).

    Returns the decoded claims dict on success.
    Raises jose.JWTError on any verification failure.
    """
    settings = get_settings()
    jwks = await get_jwks()

    try:
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Clerk JWTs have no aud by default
            issuer=settings.clerk_issuer,
        )
    except JWTError:
        # Force a JWKS refresh on next attempt in case the key rotated
        await _get_redis().delete(_JWKS_CACHE_KEY)
        raise

    return claims
