from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from api.models import UploadedFileItem
from config import get_settings
from api.services.file_service import delete_upload, list_uploads, save_upload

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    id: str = Form(...),
    name: str = Form(...),
):
    if not name or name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    contents = await file.read()
    s = get_settings()
    if len(contents) > s.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {s.MAX_UPLOAD_SIZE_MB}MB",
        )

    uploaded_at = save_upload(contents, id, name)
    return {"status": "ok", "id": id, "uploaded_at": uploaded_at}


@router.get("/list", response_model=list[UploadedFileItem])
def list_uploaded_files():
    return list_uploads()


@router.delete("/delete/{file_id}")
def delete_file(file_id: str):
    if not delete_upload(file_id):
        raise HTTPException(status_code=404, detail="File not found")
    return {"status": "deleted"}
