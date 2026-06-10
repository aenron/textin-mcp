from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP


TableView = Literal["markdown", "html"]


@dataclass(frozen=True)
class ParseOptions:
    page_range: str | None = None
    password: str | None = None
    include_hierarchy: bool | None = None
    include_inline_objects: bool | None = None
    include_char_details: bool | None = None
    include_image_data: bool | None = None
    include_table_structure: bool | None = None
    pages: bool | None = None
    title_tree: bool | None = None
    table_view: TableView | None = None


def _load_xparse_symbols() -> tuple[Any, Any, Any, Any]:
    try:
        from xparse_client import Capabilities, ParseConfig, Scope, XParseClient
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency xparse-client. Install it with `pip install -r requirements.txt`."
        ) from exc

    try:
        from xparse_client import Document
    except ImportError:
        from xparse_client.models import DocumentConfig as Document

    return XParseClient, ParseConfig, Capabilities, Scope, Document


def _drop_none(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _build_parse_config(options: ParseOptions) -> Any:
    _, ParseConfig, Capabilities, Scope, Document = _load_xparse_symbols()

    capabilities_values = _drop_none(
        {
            "include_hierarchy": options.include_hierarchy,
            "include_inline_objects": options.include_inline_objects,
            "include_char_details": options.include_char_details,
            "include_image_data": options.include_image_data,
            "include_table_structure": options.include_table_structure,
            "pages": options.pages,
            "title_tree": options.title_tree,
            "table_view": options.table_view,
        }
    )
    config_values: dict[str, Any] = {}
    if capabilities_values:
        config_values["capabilities"] = Capabilities(**capabilities_values)
    if options.page_range:
        config_values["scope"] = Scope(page_range=options.page_range)
    if options.password:
        config_values["document"] = Document(password=options.password)
    return ParseConfig(**config_values) if config_values else None


def _client() -> Any:
    XParseClient, _, _, _, _ = _load_xparse_symbols()
    server_url = os.getenv("TEXTIN_SERVER_URL")
    if server_url:
        return XParseClient(server_url=server_url)
    return XParseClient()


def _max_file_bytes() -> int:
    return int(os.getenv("MAX_FILE_BYTES", str(50 * 1024 * 1024)))


def _document_from_base64(filename: str, file_base64: str) -> tuple[str, BytesIO]:
    safe_name = Path(filename).name
    if not safe_name:
        raise ValueError("filename must not be empty")
    try:
        content = base64.b64decode(file_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("file_base64 must be valid base64 content") from exc
    max_file_bytes = _max_file_bytes()
    if len(content) > max_file_bytes:
        raise ValueError(f"Decoded file exceeds MAX_FILE_BYTES ({max_file_bytes})")
    return safe_name, BytesIO(content)


def _to_plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return _to_plain(value.model_dump())
    if hasattr(value, "dict"):
        return _to_plain(value.dict())
    if hasattr(value, "__dict__"):
        return _to_plain(vars(value))
    return str(value)


def _result_summary(result: Any) -> dict[str, Any]:
    plain = _to_plain(result)
    if not isinstance(plain, dict):
        return {"result": plain}

    elements = plain.get("elements")
    pages = plain.get("pages")
    return {
        "x_request_id": plain.get("x_request_id"),
        "markdown": plain.get("markdown"),
        "elements": elements,
        "title_tree": plain.get("title_tree"),
        "pages": pages,
        "element_count": len(elements) if isinstance(elements, list) else None,
        "page_count": len(pages) if isinstance(pages, list) else None,
        "raw": plain,
    }


def create_server() -> FastMCP:
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8000"))
    mcp = FastMCP("textin-xparse", host=host, port=port)

    @mcp.tool()
    def parse_run(
        filename: str,
        file_base64: str,
        page_range: str | None = None,
        password: str | None = None,
        include_hierarchy: bool | None = None,
        include_inline_objects: bool | None = None,
        include_char_details: bool | None = None,
        include_image_data: bool | None = None,
        include_table_structure: bool | None = None,
        pages: bool | None = None,
        title_tree: bool | None = None,
        table_view: TableView | None = None,
    ) -> dict[str, Any]:
        """Synchronously parse a document with TextIn xParse."""
        safe_name, file = _document_from_base64(filename, file_base64)
        config = _build_parse_config(
            ParseOptions(
                page_range=page_range,
                password=password,
                include_hierarchy=include_hierarchy,
                include_inline_objects=include_inline_objects,
                include_char_details=include_char_details,
                include_image_data=include_image_data,
                include_table_structure=include_table_structure,
                pages=pages,
                title_tree=title_tree,
                table_view=table_view,
            )
        )
        kwargs = {"file": file, "filename": safe_name}
        if config is not None:
            kwargs["config"] = config
        result = _client().parse.run(**kwargs)
        return _result_summary(result)

    @mcp.tool()
    def parse_create_job(
        filename: str,
        file_base64: str,
        webhook: str | None = None,
        page_range: str | None = None,
        password: str | None = None,
        include_hierarchy: bool | None = None,
        include_inline_objects: bool | None = None,
        include_char_details: bool | None = None,
        include_image_data: bool | None = None,
        include_table_structure: bool | None = None,
        pages: bool | None = None,
        title_tree: bool | None = None,
        table_view: TableView | None = None,
    ) -> dict[str, Any]:
        """Create an asynchronous TextIn xParse job."""
        safe_name, file = _document_from_base64(filename, file_base64)
        config = _build_parse_config(
            ParseOptions(
                page_range=page_range,
                password=password,
                include_hierarchy=include_hierarchy,
                include_inline_objects=include_inline_objects,
                include_char_details=include_char_details,
                include_image_data=include_image_data,
                include_table_structure=include_table_structure,
                pages=pages,
                title_tree=title_tree,
                table_view=table_view,
            )
        )
        kwargs = {"file": file, "filename": safe_name}
        if webhook:
            kwargs["webhook"] = webhook
        if config is not None:
            kwargs["config"] = config
        result = _client().parse.create_job(**kwargs)
        return _to_plain(result)

    @mcp.tool()
    def parse_get_job(job_id: str) -> dict[str, Any]:
        """Get an asynchronous TextIn xParse job status."""
        return _to_plain(_client().parse.get_job(job_id=job_id))

    @mcp.tool()
    def parse_wait_job(
        job_id: str,
        timeout: float = 300.0,
        poll_interval: float = 5.0,
        download_result: bool = False,
    ) -> dict[str, Any]:
        """Wait for an asynchronous TextIn xParse job to complete."""
        result = _client().parse.wait_job(
            job_id=job_id,
            timeout=timeout,
            poll_interval=poll_interval,
        )
        plain = _to_plain(result)
        if download_result and isinstance(plain, dict) and plain.get("result_url"):
            import httpx

            response = httpx.get(plain["result_url"], timeout=timeout)
            response.raise_for_status()
            try:
                plain["downloaded_result"] = response.json()
            except json.JSONDecodeError:
                plain["downloaded_result"] = response.text
        return plain

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="TextIn xParse SSE MCP server")
    parser.add_argument("--transport", choices=["sse", "stdio", "streamable-http"], default="sse")
    args = parser.parse_args()
    create_server().run(transport=args.transport)


if __name__ == "__main__":
    main()
