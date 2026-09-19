from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from ..dependencies import client_ip, current_user, get_profile, state


router = APIRouter(prefix="/api/files", tags=["files"])
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")


def _safe_filename(value: str) -> str:
    name = Path(value or "upload").name.replace("\x00", "").strip()
    name = _SAFE_NAME.sub("_", name).strip(" .")
    return (name or "upload")[:180]


def _public_upload(item: dict) -> dict:
    result = {key: value for key, value in item.items() if key != "path"}
    result["hermes_path"] = item.get("path", "")
    result["suggested_reference"] = f'Use the uploaded file at "{item.get("path", "")}".'
    return result


async def _scan(request: Request, path: Path) -> tuple[str, str]:
    command = state(request).settings.upload_scan_command
    if not command:
        return "not_configured", "No malware scanner command is configured; structural validation only."
    try:
        process = await asyncio.create_subprocess_exec(
            *command, str(path), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=state(request).settings.upload_scan_timeout_seconds
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=422, detail="Upload scanner timed out") from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Upload scanner could not be started") from exc
    detail = (stdout + stderr).decode("utf-8", errors="replace")[-800:]
    if process.returncode != 0:
        raise HTTPException(status_code=422, detail="Upload was rejected by the configured scanner")
    return "clean", detail or "Scanner returned success."


@router.get("")
def list_files(
    request: Request, profile: str | None = None, limit: int = 100,
    user: dict = Depends(current_user),
) -> dict:
    selected = None
    if profile:
        selected = get_profile(request, profile, user=user).slug
    return {
        "files": [
            _public_upload(item)
            for item in state(request).db.list_uploads(user["id"], profile=selected, limit=limit)
        ],
        "max_upload_bytes": state(request).settings.max_upload_bytes,
        "allowed_extensions": list(state(request).settings.upload_allowed_extensions),
        "scanner_configured": bool(state(request).settings.upload_scan_command),
    }


@router.post("")
async def upload_file(
    request: Request,
    profile: str = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(current_user),
) -> dict:
    spec = get_profile(request, profile, user=user, permission="files_write")
    settings = state(request).settings
    original_name = _safe_filename(file.filename or "upload")
    extension = Path(original_name).suffix.lower()
    if extension not in settings.upload_allowed_extensions:
        raise HTTPException(status_code=415, detail=f"File extension {extension or '(none)'} is not allowed")

    upload_id = str(uuid.uuid4())
    target_dir = settings.upload_root / user["id"] / spec.slug / upload_id
    target_dir.mkdir(parents=True, exist_ok=False)
    stored_name = original_name
    target = (target_dir / stored_name).resolve()
    try:
        target.relative_to(settings.upload_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload path") from exc

    digest = hashlib.sha256()
    size = 0
    try:
        with target.open("xb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Uploaded file is too large")
                digest.update(chunk)
                handle.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        scan_status, scan_detail = await _scan(request, target)
        item = state(request).db.create_upload(
            upload_id=upload_id,
            user_id=user["id"],
            profile=spec.slug,
            original_name=original_name,
            stored_name=stored_name,
            path=str(target),
            mime_type=file.content_type or "application/octet-stream",
            size_bytes=size,
            sha256=digest.hexdigest(),
            scan_status=scan_status,
            scan_detail=scan_detail,
        )
    except Exception:
        try:
            target.unlink(missing_ok=True)
            target_dir.rmdir()
        except OSError:
            pass
        raise
    finally:
        await file.close()

    state(request).db.audit(
        event="file.uploaded", user_id=user["id"], profile=spec.slug, ip=client_ip(request),
        metadata={
            "upload_id": upload_id, "name": original_name, "bytes": size,
            "sha256": digest.hexdigest(), "scan_status": item["scan_status"],
        },
    )
    return _public_upload(item)


@router.get("/{upload_id}/download")
def download_file(
    request: Request, upload_id: str, user: dict = Depends(current_user)
):
    item = state(request).db.get_upload(user["id"], upload_id)
    if not item:
        raise HTTPException(status_code=404, detail="File not found")
    get_profile(request, item["profile"], user=user)
    path = Path(item["path"]).resolve()
    try:
        path.relative_to(state(request).settings.upload_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=410, detail="File record exists but content is unavailable")
    return FileResponse(
        path,
        media_type=item["mime_type"] or "application/octet-stream",
        filename=item["original_name"],
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete("/{upload_id}")
def delete_file(
    request: Request, upload_id: str, user: dict = Depends(current_user)
) -> dict:
    existing = state(request).db.get_upload(user["id"], upload_id)
    if not existing:
        raise HTTPException(status_code=404, detail="File not found")
    get_profile(request, existing["profile"], user=user, permission="files_write")
    item = state(request).db.delete_upload(user["id"], upload_id)
    path = Path(item["path"])
    try:
        resolved = path.resolve()
        resolved.relative_to(state(request).settings.upload_root.resolve())
        resolved.unlink(missing_ok=True)
        try:
            resolved.parent.rmdir()
        except OSError:
            pass
    except (OSError, ValueError):
        pass
    state(request).db.audit(
        event="file.deleted", user_id=user["id"], profile=item["profile"], ip=client_ip(request),
        metadata={"upload_id": upload_id, "name": item["original_name"]},
    )
    return {"ok": True}
