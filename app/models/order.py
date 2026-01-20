from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_username: Mapped[str] = mapped_column(String(64), index=True)
    product_variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id")
    )
    points_spent: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="new")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
