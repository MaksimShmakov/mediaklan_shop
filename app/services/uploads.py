import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

from app.core.config import ALLOWED_IMAGE_EXTS, UPLOAD_DIR


def save_image_upload(image_file: Optional[UploadFile]) -> Optional[str]:
    if not image_file or not image_file.filename:
        return None
    if image_file.content_type and not image_file.content_type.startswith(
        "image/"
    ):
        raise HTTPException(status_code=400, detail="Нужна картинка (image/*)")
    ext = Path(image_file.filename).suffix.lower()
    if not ext or ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            status_code=400,
            detail="Формат изображения: JPG, PNG, WebP, GIF, AVIF",
        )
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    destination = UPLOAD_DIR / filename
    with destination.open("wb") as buffer:
        shutil.copyfileobj(image_file.file, buffer)
    return f"/static/uploads/{filename}"


def delete_image_file(image_url: Optional[str]) -> None:
    if not image_url or not image_url.startswith("/static/uploads/"):
        return
    filename = Path(image_url).name
    if not filename:
        return
    try:
        (UPLOAD_DIR / filename).unlink(missing_ok=True)
    except OSError:
        pass
