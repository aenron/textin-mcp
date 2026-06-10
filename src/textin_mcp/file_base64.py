from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse


def _max_file_bytes() -> int:
    return int(os.getenv("MAX_FILE_BYTES", str(50 * 1024 * 1024)))


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


def _file_payload(file_id: str, metadata: dict[str, Any], content: bytes) -> dict[str, Any]:
    return {
        "file_id": file_id,
        "filename": metadata["filename"],
        "mime_type": metadata["mime_type"],
        "size": len(content),
        "base64": base64.b64encode(content).decode("ascii"),
    }


def create_app() -> FastAPI:
    app = FastAPI(title="TextIn file base64 helper")

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
    async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
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
        return {
            "file_id": file_id,
            **metadata,
            "download_url": f"/files/{file_id}",
            "base64_url": f"/files/{file_id}/base64",
        }

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
