from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AllowlistEntry, ShopSettings


def get_shop_settings(db: Session, shop_type: str) -> Optional[ShopSettings]:
    return db.execute(
        select(ShopSettings).where(ShopSettings.shop_type == shop_type)
    ).scalar_one_or_none()


def is_shop_open(settings: Optional[ShopSettings], now: datetime) -> bool:
    if not settings or not settings.opens_at or not settings.closes_at:
        return False
    return settings.opens_at <= now <= settings.closes_at


def has_access(db: Session, tg_username: str, shop_type: str) -> bool:
    entry = db.execute(
        select(AllowlistEntry).where(
            AllowlistEntry.tg_username == tg_username,
            AllowlistEntry.shop_type == shop_type,
        )
    ).scalar_one_or_none()
    return entry is not None
