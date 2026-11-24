import io
import uuid
import warnings
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from app.core.config import MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, UPLOAD_DIR

register_heif_opener()
IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "AVIF", "HEIF", "BMP", "TIFF"}


def save_image_upload(image_file: Optional[UploadFile]) -> Optional[str]:
    if not image_file or not image_file.filename:
        return None
    content = image_file.file.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(400, "Фото слишком большое: максимум 15 МБ")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                if source.format not in IMAGE_FORMATS:
                    raise ValueError("unsupported format")
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise HTTPException(400, "Фото слишком большое: максимум 40 мегапикселей")
                # Normalize orientation, strip metadata, convert phone formats to browser-safe PNG/JPEG.
                photo = ImageOps.exif_transpose(source)
                transparent = "A" in photo.getbands() or "transparency" in photo.info
                photo = photo.convert("RGBA" if transparent else "RGB")
                output = io.BytesIO()
                photo.save(output, format="PNG" if transparent else "JPEG", **({} if transparent else {"quality": 90}))
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(400, "Фото слишком большое: максимум 40 мегапикселей")
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise HTTPException(400, "Не удалось прочитать фото. Поддерживаются JPG/JPEG, PNG, WebP, GIF, AVIF, HEIC/HEIF, BMP и TIFF")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{'.png' if transparent else '.jpg'}"
    (UPLOAD_DIR / filename).write_bytes(output.getvalue())
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
