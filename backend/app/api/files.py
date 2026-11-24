import asyncio
import hashlib
import mimetypes
import re
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.core.sessions import require_csrf, require_identity
from app.db.models import FileAsset
from app.db.session import get_db_session

router = APIRouter(prefix="/files", tags=["Files"])

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".htm", ".css", ".java",
    ".c", ".h", ".cpp", ".hpp", ".sql", ".sh", ".ps1", ".toml", ".ini", ".log",
}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".pptx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
ARCHIVE_EXTENSIONS = {".zip"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS | ARCHIVE_EXTENSIONS
MAX_FILES_PER_REQUEST = 5
MAX_EXTRACTED_CHARS = 60_000


def _safe_filename(value: str) -> str:
    name = Path(value.replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return (name or "upload")[:255]


def _validate_file(filename: str, data: bytes) -> tuple[str, str]:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {extension or 'unknown'}")
    if not data:
        raise HTTPException(status_code=400, detail="Empty files cannot be uploaded.")

    if extension == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="The file does not have a valid PDF signature.")
    if extension in {".docx", ".xlsx", ".pptx", ".zip"}:
        if not zipfile.is_zipfile(BytesIO(data)):
            raise HTTPException(status_code=400, detail="The archive-based document is invalid.")
        if extension != ".zip":
            with zipfile.ZipFile(BytesIO(data)) as archive:
                total_uncompressed = sum(info.file_size for info in archive.infolist())
                oversized_member = any(info.file_size > 50 * 1024 * 1024 for info in archive.infolist())
                suspicious_ratio = any(
                    info.compress_size > 0 and info.file_size / info.compress_size > 200
                    for info in archive.infolist()
                )
            if total_uncompressed > 200 * 1024 * 1024 or oversized_member or suspicious_ratio:
                raise HTTPException(
                    status_code=413,
                    detail="The compressed document expands beyond the safe processing limits.",
                )
    if extension == ".doc" and not data.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        raise HTTPException(status_code=400, detail="The legacy Word document signature is invalid.")
    if extension == ".png" and not data.startswith(bytes.fromhex("89504E470D0A1A0A")):
        raise HTTPException(status_code=400, detail="The PNG signature is invalid.")
    if extension in {".jpg", ".jpeg"} and not data.startswith(bytes.fromhex("FFD8FF")):
        raise HTTPException(status_code=400, detail="The JPEG signature is invalid.")
    if extension == ".gif" and not data.startswith((b"GIF87a", b"GIF89a")):
        raise HTTPException(status_code=400, detail="The GIF signature is invalid.")
    if extension == ".webp" and not (
        data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    ):
        raise HTTPException(status_code=400, detail="The WebP signature is invalid.")
    if extension == ".svg":
        try:
            svg_text = data.decode("utf-8-sig").lstrip().lower()
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="The SVG file is not valid UTF-8.") from exc
        if not (svg_text.startswith("<svg") or svg_text.startswith("<?xml")):
            raise HTTPException(status_code=400, detail="The SVG document is invalid.")
    if extension in TEXT_EXTENSIONS:
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400, detail="Text and source files must use UTF-8 encoding."
            ) from exc
        if b"\x00" in data:
            raise HTTPException(status_code=400, detail="Binary content is not accepted as a text file.")

    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return extension, media_type


def _extract_text(extension: str, data: bytes) -> str:
    text = ""
    if extension in TEXT_EXTENSIONS:
        text = data.decode("utf-8-sig", errors="replace")
    elif extension == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages[:100])
    elif extension == ".docx":
        from docx import Document

        document = Document(BytesIO(data))
        chunks = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
        for table in document.tables:
            for row in table.rows:
                chunks.append(" | ".join(cell.text for cell in row.cells))
        text = "\n".join(chunks)
    elif extension == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
        chunks = []
        try:
            for sheet in workbook.worksheets[:20]:
                chunks.append(f"## Sheet: {sheet.title}")
                for row_index, row in enumerate(sheet.iter_rows(values_only=True)):
                    if row_index >= 1000:
                        chunks.append("[Further rows omitted]")
                        break
                    values = ["" if value is None else str(value) for value in row[:50]]
                    if any(values):
                        chunks.append(" | ".join(values))
        finally:
            workbook.close()
        text = "\n".join(chunks)
    elif extension == ".pptx":
        from pptx import Presentation

        presentation = Presentation(BytesIO(data))
        chunks = []
        for slide_index, slide in enumerate(presentation.slides[:100], start=1):
            chunks.append(f"## Slide {slide_index}")
            for shape in slide.shapes:
                if getattr(shape, "has_text_frame", False) and shape.text.strip():
                    chunks.append(shape.text)
        text = "\n".join(chunks)
    elif extension == ".zip":
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entries = [
                info.filename for info in archive.infolist()[:300]
                if not info.is_dir()
            ]
        text = "ZIP archive contents (files are listed only; nothing is extracted):\n" + "\n".join(entries)
    elif extension == ".doc":
        text = (
            "Legacy .doc file received. This foundation can securely store and download it, "
            "but legacy binary Word text extraction is not enabled yet."
        )
    elif extension in IMAGE_EXTENSIONS:
        text = (
            f"Image file received ({extension}). The image is stored privately; "
            "OCR and provider image understanding are planned but not enabled yet."
        )

    return text[:MAX_EXTRACTED_CHARS]


def _r2_client():
    if not all((settings.r2_account_id, settings.r2_bucket_name,
                settings.r2_access_key_id, settings.r2_secret_access_key)):
        raise HTTPException(
            status_code=503,
            detail="Cloudflare R2 is selected but its server credentials are not configured.",
        )
    import boto3

    endpoint = settings.r2_endpoint_url or (
        f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def _object_key(user_id: UUID, storage_filename: str) -> str:
    return f"users/{user_id}/{storage_filename}"


def _write_storage(user_id: UUID, storage_filename: str, data: bytes) -> None:
    if settings.storage_backend.lower() == "r2":
        _r2_client().put_object(
            Bucket=settings.r2_bucket_name,
            Key=_object_key(user_id, storage_filename),
            Body=data,
            ContentType="application/octet-stream",
        )
        return
    path = _storage_path(user_id, storage_filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _read_storage(user_id: UUID, storage_filename: str) -> bytes:
    if settings.storage_backend.lower() == "r2":
        response = _r2_client().get_object(
            Bucket=settings.r2_bucket_name,
            Key=_object_key(user_id, storage_filename),
        )
        return response["Body"].read()
    return _storage_path(user_id, storage_filename).read_bytes()


def _delete_storage(user_id: UUID, storage_filename: str) -> None:
    if settings.storage_backend.lower() == "r2":
        _r2_client().delete_object(
            Bucket=settings.r2_bucket_name,
            Key=_object_key(user_id, storage_filename),
        )
        return
    try:
        _storage_path(user_id, storage_filename).unlink()
    except FileNotFoundError:
        pass


def _storage_path(user_id: UUID, storage_filename: str) -> Path:
    root = Path(settings.storage_root).resolve()
    user_root = (root / str(user_id)).resolve()
    path = (user_root / storage_filename).resolve()
    if not path.is_relative_to(user_root):
        raise HTTPException(status_code=400, detail="Invalid storage path.")
    return path


async def _owned_file(
    session: AsyncSession,
    user_id: UUID,
    file_id: UUID,
) -> FileAsset:
    asset = await session.scalar(
        select(FileAsset).where(FileAsset.id == file_id, FileAsset.user_id == user_id)
    )
    if not asset:
        raise HTTPException(status_code=404, detail="File not found.")
    return asset


@router.get("")
async def list_files(
    identity: Annotated[dict, Depends(require_identity)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    user_id = UUID(str(identity["user_id"])) if identity.get("user_id") else None
    if not user_id:
        return {"data": []}
    assets = await session.scalars(
        select(FileAsset)
        .where(FileAsset.user_id == user_id)
        .order_by(FileAsset.created_at.desc())
        .limit(100)
    )
    return {
        "data": [
            {
                "id": str(asset.id),
                "filename": asset.original_filename,
                "media_type": asset.media_type,
                "size_bytes": asset.size_bytes,
                "created_at": asset.created_at.isoformat() if asset.created_at else None,
            }
            for asset in assets
        ]
    }


@router.post(
    "/upload",
    dependencies=[Depends(require_csrf), Depends(enforce_rate_limit)],
)
async def upload_files(
    files: Annotated[list[UploadFile], File(...)],
    identity: Annotated[dict, Depends(require_identity)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    user_id = UUID(str(identity["user_id"])) if identity.get("user_id") else None
    if not user_id:
        raise HTTPException(status_code=403, detail="Sign in to upload and save files.")
    if not files or len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Upload between 1 and {MAX_FILES_PER_REQUEST} files at a time.",
        )

    plan = identity.get("plan", "free")
    max_bytes = (
        settings.premium_max_upload_size_mb
        if plan in {"premium", "pro", "lifetime_premium"} or identity.get("role") == "admin"
        else settings.free_max_upload_size_mb
    ) * 1024 * 1024

    if settings.storage_backend.lower() == "local":
        user_root = (Path(settings.storage_root).resolve() / str(user_id))
        await asyncio.to_thread(user_root.mkdir, parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(user_root.chmod, 0o700)
        except OSError:
            pass
    elif settings.storage_backend.lower() != "r2":
        raise HTTPException(status_code=500, detail="Unsupported file storage backend.")

    uploaded: list[dict] = []
    written_objects: list[str] = []
    try:
        for upload in files:
            filename = _safe_filename(upload.filename or "upload")
            data = await upload.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"{filename} exceeds your {max_bytes // (1024 * 1024)} MB upload limit.",
                )
            extension, media_type = _validate_file(filename, data)
            try:
                extracted = await asyncio.to_thread(_extract_text, extension, data)
            except Exception as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"{filename} could not be safely parsed.",
                ) from exc
            storage_filename = f"{uuid.uuid4().hex}{extension}"
            await asyncio.to_thread(_write_storage, user_id, storage_filename, data)
            written_objects.append(storage_filename)

            asset = FileAsset(
                user_id=user_id,
                original_filename=filename,
                storage_filename=storage_filename,
                media_type=media_type,
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                extracted_text=extracted,
            )
            session.add(asset)
            await session.flush()
            uploaded.append(
                {
                    "id": str(asset.id),
                    "filename": filename,
                    "media_type": media_type,
                    "size_bytes": len(data),
                    "extracted_text": extracted,
                    "text_available": bool(extracted),
                }
            )
        await session.commit()
    except Exception:
        await session.rollback()
        for storage_filename in written_objects:
            try:
                await asyncio.to_thread(_delete_storage, user_id, storage_filename)
            except Exception:
                pass
        raise
    finally:
        for upload in files:
            await upload.close()

    return {"data": uploaded}


@router.get("/{file_id}/download")
async def download_file(
    file_id: UUID,
    identity: Annotated[dict, Depends(require_identity)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    user_id = UUID(str(identity["user_id"])) if identity.get("user_id") else None
    if not user_id:
        raise HTTPException(status_code=403, detail="Sign in to download saved files.")
    asset = await _owned_file(session, user_id, file_id)
    try:
        data = await asyncio.to_thread(_read_storage, user_id, asset.storage_filename)
    except Exception as exc:
        if getattr(exc, "response", {}).get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
            raise HTTPException(status_code=404, detail="Stored file is missing.") from exc
        raise HTTPException(status_code=503, detail="File storage is temporarily unavailable.") from exc
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{asset.original_filename}"'},
    )


@router.delete(
    "/{file_id}",
    dependencies=[Depends(require_csrf)],
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_file(
    file_id: UUID,
    identity: Annotated[dict, Depends(require_identity)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    user_id = UUID(str(identity["user_id"])) if identity.get("user_id") else None
    if not user_id:
        raise HTTPException(status_code=403, detail="Sign in to delete saved files.")
    asset = await _owned_file(session, user_id, file_id)
    storage_filename = asset.storage_filename
    await session.delete(asset)
    await session.commit()
    await asyncio.to_thread(_delete_storage, user_id, storage_filename)
