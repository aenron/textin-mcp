from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile


def _max_file_bytes() -> int:
    return int(os.getenv("MAX_FILE_BYTES", str(50 * 1024 * 1024)))


def create_app() -> FastAPI:
    app = FastAPI(title="TextIn file base64 helper")

    @app.post("/file-to-base64")
    async def file_to_base64(file: UploadFile = File(...)) -> dict[str, Any]:
        content = await file.read()
        max_file_bytes = _max_file_bytes()
        if len(content) > max_file_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Uploaded file exceeds MAX_FILE_BYTES ({max_file_bytes})",
            )
        filename = Path(file.filename or "document").name
        return {
            "filename": filename,
            "mime_type": file.content_type,
            "size": len(content),
            "base64": base64.b64encode(content).decode("ascii"),
        }

    return app


def main() -> None:
    import uvicorn

    host = os.getenv("FILE_BASE64_HOST", "0.0.0.0")
    port = int(os.getenv("FILE_BASE64_PORT", "8001"))
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
