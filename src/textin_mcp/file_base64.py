from __future__ import annotations

import base64
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse


def _max_file_bytes() -> int:
    return int(os.getenv("MAX_FILE_BYTES", str(50 * 1024 * 1024)))


def _file_retention_seconds() -> int:
    return int(os.getenv("FILE_RETENTION_SECONDS", str(7 * 24 * 60 * 60)))


def _cleanup_interval_seconds() -> int:
    return int(os.getenv("FILE_CLEANUP_INTERVAL_SECONDS", str(60 * 60)))


def _storage_dir() -> Path:
    storage_dir = Path(os.getenv("FILE_STORAGE_DIR", "/data/files"))
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def _safe_filename(filename: str | None) -> str:
    return Path(filename or "document").name


def _metadata_path(file_id: str) -> Path:
    return _storage_dir() / f"{file_id}.json"


def _file_path(file_id: str) -> Path:
    return _storage_dir() / file_id


def _read_metadata(file_id: str) -> dict[str, Any]:
    metadata_path = _metadata_path(file_id)
    file_path = _file_path(file_id)
    if not metadata_path.is_file() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _cleanup_expired_files(now: float | None = None) -> dict[str, int]:
    retention_seconds = _file_retention_seconds()
    if retention_seconds <= 0:
        return {"deleted_files": 0}

    cutoff = (now if now is not None else time.time()) - retention_seconds
    deleted_files = 0
    for path in _storage_dir().iterdir():
        if not path.is_file() or path.stat().st_mtime >= cutoff:
            continue
        path.unlink()
        deleted_files += 1
    return {"deleted_files": deleted_files}


async def _cleanup_loop() -> None:
    while True:
        _cleanup_expired_files()
        await asyncio.sleep(_cleanup_interval_seconds())


def _file_payload(file_id: str, metadata: dict[str, Any], content: bytes) -> dict[str, Any]:
    return {
        "file_id": file_id,
        "filename": metadata["filename"],
        "mime_type": metadata["mime_type"],
        "size": len(content),
        "base64": base64.b64encode(content).decode("ascii"),
    }


def _public_base_url(request: Request) -> str:
    configured = os.getenv("FILE_PUBLIC_BASE_URL")
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


def _upload_payload(file_id: str, metadata: dict[str, Any], base_url: str) -> dict[str, Any]:
    return {
        "file_id": file_id,
        **metadata,
        "download_url": f"{base_url}/files/{file_id}",
        "base64_url": f"{base_url}/files/{file_id}/base64",
    }


def _upload_result_html(payload: dict[str, Any]) -> str:
    filename = payload["filename"]
    download_url = payload["download_url"]
    base64_url = payload["base64_url"]
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Upload complete</title>
    <style>
      body {{
        font-family: Arial, sans-serif;
        max-width: 760px;
        margin: 48px auto;
        padding: 0 24px;
        color: #1f2937;
      }}
      .panel {{
        border: 1px solid #d1d5db;
        border-radius: 8px;
        padding: 24px;
        background: #f9fafb;
      }}
      dt {{
        font-weight: 700;
        margin-top: 16px;
      }}
      dd {{
        margin: 6px 0 0;
        overflow-wrap: anywhere;
      }}
      a.button {{
        display: inline-block;
        margin: 18px 12px 0 0;
        padding: 10px 14px;
        border-radius: 6px;
        background: #2563eb;
        color: white;
        text-decoration: none;
      }}
      a.secondary {{
        background: #4b5563;
      }}
    </style>
  </head>
  <body>
    <div class="panel">
      <h1>Upload complete</h1>
      <dl>
        <dt>Filename</dt>
        <dd>{filename}</dd>
        <dt>Size</dt>
        <dd>{payload["size"]} bytes</dd>
        <dt>Download URL</dt>
        <dd><a href="{download_url}">{download_url}</a></dd>
        <dt>Base64 URL</dt>
        <dd><a href="{base64_url}">{base64_url}</a></dd>
      </dl>
      <a class="button" href="{download_url}">Download file</a>
      <a class="button secondary" href="{base64_url}">Get base64 JSON</a>
      <a class="button secondary" href="/">Back to upload</a>
    </div>
  </body>
</html>
"""


def create_app() -> FastAPI:
    app = FastAPI(title="TextIn file base64 helper")

    @app.on_event("startup")
    async def start_cleanup_loop() -> None:
        app.state.cleanup_task = asyncio.create_task(_cleanup_loop())

    @app.on_event("shutdown")
    async def stop_cleanup_loop() -> None:
        cleanup_task = getattr(app.state, "cleanup_task", None)
        if cleanup_task is not None:
            cleanup_task.cancel()

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>TextIn File Upload</title>
  </head>
  <body>
    <h1>TextIn File Upload</h1>
    <form action="/upload" method="post" enctype="multipart/form-data">
      <input name="file" type="file" required>
      <button type="submit">Upload</button>
    </form>
  </body>
</html>
"""

    @app.post("/file-to-base64")
    async def file_to_base64(file: UploadFile = File(...)) -> dict[str, Any]:
        content = await file.read()
        max_file_bytes = _max_file_bytes()
        if len(content) > max_file_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Uploaded file exceeds MAX_FILE_BYTES ({max_file_bytes})",
            )
        filename = _safe_filename(file.filename)
        return {
            "filename": filename,
            "mime_type": file.content_type,
            "size": len(content),
            "base64": base64.b64encode(content).decode("ascii"),
        }

    @app.post("/upload")
    async def upload(request: Request, file: UploadFile = File(...)) -> Any:
        content = await file.read()
        max_file_bytes = _max_file_bytes()
        if len(content) > max_file_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Uploaded file exceeds MAX_FILE_BYTES ({max_file_bytes})",
            )
        file_id = uuid4().hex
        metadata = {
            "filename": _safe_filename(file.filename),
            "mime_type": file.content_type,
            "size": len(content),
        }
        _file_path(file_id).write_bytes(content)
        _metadata_path(file_id).write_text(json.dumps(metadata), encoding="utf-8")
        payload = _upload_payload(file_id, metadata, _public_base_url(request))
        if "text/html" in request.headers.get("accept", ""):
            return HTMLResponse(_upload_result_html(payload))
        return payload

    @app.get("/files/{file_id}")
    async def download(file_id: str) -> FileResponse:
        metadata = _read_metadata(file_id)
        return FileResponse(
            _file_path(file_id),
            media_type=metadata["mime_type"],
            filename=metadata["filename"],
        )

    @app.get("/files/{file_id}/base64")
    async def uploaded_file_to_base64(file_id: str) -> dict[str, Any]:
        metadata = _read_metadata(file_id)
        content = _file_path(file_id).read_bytes()
        return _file_payload(file_id, metadata, content)

    return app


def main() -> None:
    import uvicorn

    host = os.getenv("FILE_BASE64_HOST", "0.0.0.0")
    port = int(os.getenv("FILE_BASE64_PORT", "8001"))
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
