from __future__ import annotations

import base64

from fastapi.testclient import TestClient


def test_file_to_base64_returns_uploaded_file_payload():
    from textin_mcp.file_base64 import create_app

    client = TestClient(create_app())

    response = client.post(
        "/file-to-base64",
        files={"file": ("sample.pdf", b"pdf-bytes", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "filename": "sample.pdf",
        "mime_type": "application/pdf",
        "size": 9,
        "base64": base64.b64encode(b"pdf-bytes").decode("ascii"),
    }


def test_file_to_base64_rejects_files_over_limit(monkeypatch):
    from textin_mcp.file_base64 import create_app

    monkeypatch.setenv("MAX_FILE_BYTES", "4")
    client = TestClient(create_app())

    response = client.post(
        "/file-to-base64",
        files={"file": ("sample.pdf", b"pdf-bytes", "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Uploaded file exceeds MAX_FILE_BYTES (4)"}


def test_file_to_base64_sanitizes_filename():
    from textin_mcp.file_base64 import create_app

    client = TestClient(create_app())

    response = client.post(
        "/file-to-base64",
        files={"file": ("../sample.pdf", b"pdf-bytes", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "sample.pdf"
