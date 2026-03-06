from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from app.core.config import ALLOWED_IMAGE_EXTS, UPLOAD_DIR

STATIC_DIR = Path("app/static")


def _strip_query_fragment(value: str) -> str:
    return value.split("#", 1)[0].split("?", 1)[0]


def _normalize_separators(value: str) -> str:
    return value.replace("\\", "/")
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


def _resolve_local_path(raw_value: str) -> str | None:
    clean_value = _strip_query_fragment(_normalize_separators(raw_value))
    if not clean_value:
        return None

    lower_value = clean_value.lower()

    upload_markers = (
        "/static/uploads/",
        "static/uploads/",
        "/uploads/",
        "uploads/",
        "/app/static/uploads/",
        "app/static/uploads/",
    )
    for marker in upload_markers:
        marker_idx = lower_value.find(marker)
        if marker_idx == -1:
            continue
        relative_path = clean_value[marker_idx + len(marker):]
        upload_path = _normalize_upload_path(relative_path)
        if upload_path:
            return upload_path

    static_markers = (
        "/static/",
        "static/",
        "/app/static/",
        "app/static/",
    )
    for marker in static_markers:
        marker_idx = lower_value.find(marker)
        if marker_idx == -1:
            continue
        relative_path = clean_value[marker_idx + len(marker):]
        static_path = _normalize_static_path(relative_path)
        if static_path:
            return static_path

    basename = PurePosixPath(clean_value).name
    if Path(basename).suffix.lower() in ALLOWED_IMAGE_EXTS:
        upload_path = _normalize_upload_path(basename)
        if upload_path:
            return upload_path

    return None


def resolve_image_url(image_url: str | None) -> str | None:
    if not image_url:
        return None

    raw_value = image_url.strip()
    if not raw_value:
        return None

    local_path = _resolve_local_path(raw_value)
    if local_path:
        return local_path

    if raw_value.startswith("www."):
        return f"https://{raw_value}"

    if raw_value.startswith("//"):
        return f"https:{raw_value}"

    parsed = urlparse(_normalize_separators(raw_value))
    scheme = parsed.scheme.lower()
    path = parsed.path or ""

    if scheme in {"http", "https"} and parsed.netloc:
        return raw_value

    if scheme == "file":
        local_path = _resolve_local_path(path)
        if local_path:
            return local_path

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

    normalized_value = _normalize_separators(raw_value)
    return normalized_value if normalized_value.startswith("/") else None
