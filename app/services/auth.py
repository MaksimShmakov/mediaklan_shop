from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def normalize_tg_username(raw: str) -> Optional[str]:
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    if not cleaned.startswith("@"):
        cleaned = "@" + cleaned
    return cleaned.lower()


def get_current_user(request: Request, db: Session) -> Optional[User]:
    username = request.session.get("tg_username")
    if not username:
        return None
    return db.execute(
        select(User).where(User.tg_username == username)
    ).scalar_one_or_none()


def require_admin(request: Request) -> None:
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
