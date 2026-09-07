import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

UPLOAD_DIR = Path("uploads/logos")
MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2 Mo
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


async def save_shop_logo(shop_id: int, file: UploadFile) -> str:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Le logo doit être une image (PNG, JPG ou WEBP)")

    content = await file.read()
    if len(content) > MAX_LOGO_SIZE:
        raise HTTPException(status_code=400, detail="Le logo ne doit pas dépasser 2 Mo")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    extension = Path(file.filename or "").suffix or ".png"
    filename = f"shop_{shop_id}_{uuid.uuid4().hex[:8]}{extension}"
    path = UPLOAD_DIR / filename
    path.write_bytes(content)

    return str(path)
