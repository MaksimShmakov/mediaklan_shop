import os
from pathlib import Path

SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
APP_TZ = os.getenv("APP_TZ", "Europe/Moscow")

UPLOAD_DIR = Path("app/static/uploads")
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_GROUP_CHAT_ID = os.getenv("TG_GROUP_CHAT_ID")

SHOP_TYPES = ("regular", "premium")
ORDER_STATUSES = ("new", "processing", "delivered", "cancelled")
ORDER_STATUS_LABELS = {
    "new": "Новый",
    "processing": "В процессе",
    "delivered": "Доставлен",
    "cancelled": "Отменён",
}
