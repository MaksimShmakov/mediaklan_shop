import json
import urllib.request

from app.core.config import TG_BOT_TOKEN, TG_GROUP_CHAT_ID


def send_telegram_message(text: str) -> None:
    if not TG_BOT_TOKEN or not TG_GROUP_CHAT_ID:
        return
    payload = {
        "chat_id": TG_GROUP_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    data = json.dumps(payload).encode("utf-8")
    request_obj = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=5) as response:
            response.read()
    except Exception:
        return
