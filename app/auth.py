import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request, Depends
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User, UserSession

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_session(user_id, db: Session) -> str:
    token = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.session_expire_days)
    db.add(UserSession(token=token, user_id=user_id, expires_at=expires_at))
    db.commit()
    return token


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_expire_days * 24 * 3600,
        secure=settings.secure_cookies,
    )


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("session")
    if not token:
        return None
    now = datetime.now(timezone.utc)
    session = (
        db.query(UserSession)
        .filter(UserSession.token == token, UserSession.expires_at > now)
        .first()
    )
    if not session:
        return None
    return session.user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        # Raise as HTTPException so FastAPI handles it; the exception handler redirects.
        from fastapi import HTTPException
        raise HTTPException(status_code=307, headers={"Location": f"/auth/login?next={request.url.path}"})
    return user
