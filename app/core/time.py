from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import APP_TZ


def local_now() -> datetime:
    try:
        tz = ZoneInfo(APP_TZ)
    except Exception:
        return datetime.now()
    return datetime.now(tz).replace(tzinfo=None)
