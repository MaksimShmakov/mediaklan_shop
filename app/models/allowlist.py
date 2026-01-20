from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AllowlistEntry(Base):
    __tablename__ = "allowlist_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_username: Mapped[str] = mapped_column(String(64), index=True)
    shop_type: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
