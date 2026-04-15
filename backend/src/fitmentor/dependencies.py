"""FastAPI dependencies — imported by route handlers."""
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fitmentor.db.models import User
from fitmentor.db.session import get_db
from fitmentor.middleware.auth import verify_clerk_token

log = structlog.get_logger()

_bearer = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Verify the Bearer JWT, then return (or lazily create) the matching User row.

    Usage in a route:
        @router.get("/me")
        async def me(user: CurrentUser) -> ...:
            ...
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        claims = await verify_clerk_token(credentials.credentials)
    except JWTError as exc:
        log.warning("auth.jwt.invalid", error=str(exc))
        raise credentials_exception from exc

    clerk_user_id: str | None = claims.get("sub")
    if not clerk_user_id:
        raise credentials_exception

    # Pull existing user or create one on first sign-in
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            clerk_user_id=clerk_user_id,
            email=claims.get("email"),
        )
        db.add(user)
        await db.flush()  # get the generated UUID without full commit
        log.info("auth.user.created", clerk_user_id=clerk_user_id)

    return user


# Convenience type alias — use this in route signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
