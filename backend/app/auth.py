import datetime as dt

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.schemas import DemoUser

ALGORITHM = "HS256"
DEMO_USER = DemoUser(name="Demo Analyst", role="analyst")

_bearer = HTTPBearer(auto_error=False)


def issue_token(user: DemoUser, settings: Settings) -> tuple[str, int]:
    ttl = dt.timedelta(hours=settings.jwt_ttl_hours)
    now = dt.datetime.now(dt.UTC)
    claims = {"sub": user.name, "role": user.role, "iat": now, "exp": now + ttl}
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM), int(ttl.total_seconds())


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> DemoUser:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        claims = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc
    return DemoUser(name=claims["sub"], role=claims.get("role", "viewer"))
