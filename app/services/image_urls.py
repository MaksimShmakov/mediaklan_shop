from pathlib import Path
from urllib.parse import urlparse

from app.core.config import ALLOWED_IMAGE_EXTS, UPLOAD_DIR

STATIC_DIR = Path("app/static")
def _normalize_upload_path(path: str) -> str | None:
    filename = Path(path).name
    if not filename:
        return None
    if Path(filename).suffix.lower() not in ALLOWED_IMAGE_EXTS:
        return None
    return (
        f"/static/uploads/{filename}"
        if (UPLOAD_DIR / filename).exists()
        else None
    )


def _normalize_static_path(path: str) -> str | None:
    clean_path = path.lstrip("/")
    if clean_path.startswith("static/"):
        relative_path = clean_path.removeprefix("static/")
    else:
        relative_path = clean_path
    if not relative_path:
        return None
    candidate = STATIC_DIR / Path(relative_path)
    return f"/static/{relative_path}" if candidate.exists() else None


def resolve_image_url(image_url: str | None) -> str | None:
    if not image_url:
        return None

    raw_value = image_url.strip()
    if not raw_value:
        return None

    if raw_value.startswith("www."):
        return f"https://{raw_value}"

    if raw_value.startswith("//"):
        return f"https:{raw_value}"

    parsed = urlparse(raw_value)
    scheme = parsed.scheme.lower()
    path = parsed.path or ""

    if scheme in {"http", "https"} and parsed.netloc:
        return raw_value

    if path.startswith("/static/uploads/"):
        return _normalize_upload_path(path)
    if path.startswith("/uploads/"):
        return _normalize_upload_path(path)
    if path.startswith("/static/"):
        return _normalize_static_path(path)

    if raw_value.startswith("static/uploads/"):
        return _normalize_upload_path(raw_value)
    if raw_value.startswith("uploads/"):
        return _normalize_upload_path(raw_value)
    if raw_value.startswith("static/"):
        return _normalize_static_path(raw_value)

    if Path(path).name == path and Path(path).suffix.lower() in ALLOWED_IMAGE_EXTS:
        upload_path = _normalize_upload_path(path)
        if upload_path:
            return upload_path

    return raw_value if raw_value.startswith("/") else None
