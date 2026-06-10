from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


def temporary_storage_dir():
    storage_dir = Path(".file-storage-test") / uuid4().hex
    storage_dir.mkdir(parents=True, exist_ok=True)
    return str(storage_dir.resolve())


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


def test_home_page_contains_upload_form(monkeypatch):
    from textin_mcp.file_base64 import create_app

    storage_dir = temporary_storage_dir()
    monkeypatch.setenv("FILE_STORAGE_DIR", storage_dir)
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "multipart/form-data" in response.text
    assert "/upload" in response.text


def test_upload_stores_file_and_returns_links(monkeypatch):
    from textin_mcp.file_base64 import create_app

    storage_dir = temporary_storage_dir()
    monkeypatch.setenv("FILE_STORAGE_DIR", storage_dir)
    monkeypatch.setenv("FILE_PUBLIC_BASE_URL", "http://files.example.test:8005")
    client = TestClient(create_app())

    response = client.post(
        "/upload",
        files={"file": ("sample.pdf", b"pdf-bytes", "application/pdf")},
        headers={"accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "sample.pdf"
    assert payload["mime_type"] == "application/pdf"
    assert payload["size"] == 9
    assert payload["download_url"] == f"http://files.example.test:8005/files/{payload['file_id']}"
    assert payload["base64_url"] == (
        f"http://files.example.test:8005/files/{payload['file_id']}/base64"
    )
    assert (Path(storage_dir) / payload["file_id"]).read_bytes() == b"pdf-bytes"


def test_browser_upload_returns_result_page(monkeypatch):
    from textin_mcp.file_base64 import create_app

    storage_dir = temporary_storage_dir()
    monkeypatch.setenv("FILE_STORAGE_DIR", storage_dir)
    monkeypatch.setenv("FILE_PUBLIC_BASE_URL", "http://files.example.test:8005")
    client = TestClient(create_app())

    response = client.post(
        "/upload",
        files={"file": ("sample.pdf", b"pdf-bytes", "application/pdf")},
        headers={"accept": "text/html"},
    )

    assert response.status_code == 200
    assert "Upload complete" in response.text
    assert "http://files.example.test:8005/files/" in response.text
    assert "Back to upload" in response.text


def test_download_returns_uploaded_file(monkeypatch):
    from textin_mcp.file_base64 import create_app

    storage_dir = temporary_storage_dir()
    monkeypatch.setenv("FILE_STORAGE_DIR", storage_dir)
    client = TestClient(create_app())
    upload = client.post(
        "/upload",
        files={"file": ("sample.pdf", b"pdf-bytes", "application/pdf")},
    ).json()

    response = client.get(upload["download_url"])

    assert response.status_code == 200
    assert response.content == b"pdf-bytes"
    assert response.headers["content-type"] == "application/pdf"
    assert 'filename="sample.pdf"' in response.headers["content-disposition"]


def test_uploaded_file_can_be_returned_as_base64(monkeypatch):
    from textin_mcp.file_base64 import create_app

    storage_dir = temporary_storage_dir()
    monkeypatch.setenv("FILE_STORAGE_DIR", storage_dir)
    client = TestClient(create_app())
    upload = client.post(
        "/upload",
        files={"file": ("sample.pdf", b"pdf-bytes", "application/pdf")},
    ).json()

    response = client.get(upload["base64_url"])

    assert response.status_code == 200
    assert response.json() == {
        "file_id": upload["file_id"],
        "filename": "sample.pdf",
        "mime_type": "application/pdf",
        "size": 9,
        "base64": base64.b64encode(b"pdf-bytes").decode("ascii"),
    }


def test_upload_rejects_files_over_limit(monkeypatch):
    from textin_mcp.file_base64 import create_app

    storage_dir = temporary_storage_dir()
    monkeypatch.setenv("FILE_STORAGE_DIR", storage_dir)
    monkeypatch.setenv("MAX_FILE_BYTES", "4")
    client = TestClient(create_app())

    response = client.post(
        "/upload",
        files={"file": ("sample.pdf", b"pdf-bytes", "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Uploaded file exceeds MAX_FILE_BYTES (4)"}


def test_cleanup_removes_files_older_than_retention(monkeypatch):
    from textin_mcp.file_base64 import _cleanup_expired_files

    storage_dir = temporary_storage_dir()
    monkeypatch.setenv("FILE_STORAGE_DIR", storage_dir)
    monkeypatch.setenv("FILE_RETENTION_SECONDS", "10")
    old_file = Path(storage_dir) / "old-id"
    old_metadata = Path(storage_dir) / "old-id.json"
    new_file = Path(storage_dir) / "new-id"
    new_metadata = Path(storage_dir) / "new-id.json"
    old_file.write_bytes(b"old")
    old_metadata.write_text("{}", encoding="utf-8")
    new_file.write_bytes(b"new")
    new_metadata.write_text("{}", encoding="utf-8")
    old_time = time.time() - 20
    os.utime(old_file, (old_time, old_time))
    os.utime(old_metadata, (old_time, old_time))
    deleted_paths = []

    def record_unlink(path):
        deleted_paths.append(path)

    monkeypatch.setattr(Path, "unlink", record_unlink)

    result = _cleanup_expired_files()

    assert result == {"deleted_files": 2}
    assert old_file in deleted_paths
    assert old_metadata in deleted_paths
    assert new_file not in deleted_paths
    assert new_metadata not in deleted_paths


def test_cleanup_is_disabled_when_retention_is_zero(monkeypatch):
    from textin_mcp.file_base64 import _cleanup_expired_files

    storage_dir = temporary_storage_dir()
    monkeypatch.setenv("FILE_STORAGE_DIR", storage_dir)
    monkeypatch.setenv("FILE_RETENTION_SECONDS", "0")
    old_file = Path(storage_dir) / "old-id"
    old_file.write_bytes(b"old")
    old_time = time.time() - 20
    os.utime(old_file, (old_time, old_time))

    result = _cleanup_expired_files()

    assert result == {"deleted_files": 0}
    assert old_file.exists()
