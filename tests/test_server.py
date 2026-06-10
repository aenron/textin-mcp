from __future__ import annotations

import base64
import importlib
import inspect
import sys
import types


def install_fake_xparse() -> None:
    module = types.ModuleType("xparse_client")
    module.client_calls = []
    module.parse_calls = []

    class Record:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def model_dump(self):
            return self.kwargs

    class XParseClient:
        def __init__(self, **kwargs):
            module.client_calls.append(kwargs)
            self.parse = Parse()

    class Parse:
        def run(self, **kwargs):
            module.parse_calls.append(("run", _plain_parse_kwargs(kwargs)))
            return {"markdown": "ok", "elements": [], "pages": []}

        def create_job(self, **kwargs):
            module.parse_calls.append(("create_job", _plain_parse_kwargs(kwargs)))
            return {"job_id": "job-1"}

    module.XParseClient = XParseClient
    module.ParseConfig = type("ParseConfig", (Record,), {})
    module.Capabilities = type("Capabilities", (Record,), {})
    module.Scope = type("Scope", (Record,), {})
    module.Document = type("Document", (Record,), {})
    sys.modules["xparse_client"] = module


def _plain_parse_kwargs(kwargs):
    plain = dict(kwargs)
    file = plain.pop("file")
    plain["file_content"] = file.read()
    return plain


def install_fake_xparse_with_document_config() -> None:
    module = types.ModuleType("xparse_client")
    models = types.ModuleType("xparse_client.models")

    class Record:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def model_dump(self):
            return self.kwargs

    class XParseClient:
        pass

    module.XParseClient = XParseClient
    module.ParseConfig = type("ParseConfig", (Record,), {})
    module.Capabilities = type("Capabilities", (Record,), {})
    module.Scope = type("Scope", (Record,), {})
    models.DocumentConfig = type("DocumentConfig", (Record,), {})
    sys.modules["xparse_client"] = module
    sys.modules["xparse_client.models"] = models


def test_parse_options_do_not_include_credentials():
    from textin_mcp.server import create_server

    server = create_server()
    tools = server._tool_manager._tools

    assert set(tools) == {
        "parse_run",
        "parse_create_job",
        "parse_get_job",
        "parse_wait_job",
    }
    for tool in tools.values():
        schema_text = str(tool.parameters)
        assert "app_id" not in schema_text
        assert "secret" not in schema_text.lower()
        assert "TEXTIN_APP_ID" not in schema_text
        assert "TEXTIN_SECRET_CODE" not in schema_text


def test_parse_tools_accept_base64_document_content():
    from textin_mcp.server import create_server

    server = create_server()
    tools = server._tool_manager._tools

    for name in ("parse_run", "parse_create_job"):
        schema_text = str(tools[name].parameters)
        assert "filename" in schema_text
        assert "file_base64" in schema_text
        assert "file_path" not in schema_text


def test_build_parse_config_uses_documented_fields(monkeypatch):
    install_fake_xparse()
    server = importlib.reload(importlib.import_module("textin_mcp.server"))

    config = server._build_parse_config(
        server.ParseOptions(
            page_range="1-10",
            password="pw",
            include_hierarchy=True,
            include_inline_objects=True,
            include_char_details=True,
            include_image_data=True,
            include_table_structure=True,
            pages=True,
            title_tree=True,
            table_view="markdown",
        )
    )

    assert config.kwargs["scope"].kwargs == {"page_range": "1-10"}
    assert config.kwargs["document"].kwargs == {"password": "pw"}
    assert config.kwargs["capabilities"].kwargs == {
        "include_hierarchy": True,
        "include_inline_objects": True,
        "include_char_details": True,
        "include_image_data": True,
        "include_table_structure": True,
        "pages": True,
        "title_tree": True,
        "table_view": "markdown",
    }


def test_build_parse_config_supports_document_config_fallback(monkeypatch):
    install_fake_xparse_with_document_config()
    server = importlib.reload(importlib.import_module("textin_mcp.server"))

    config = server._build_parse_config(server.ParseOptions(password="pw"))

    assert config.kwargs["document"].kwargs == {"password": "pw"}


def test_client_uses_default_sdk_server_when_server_url_is_not_configured(monkeypatch):
    install_fake_xparse()
    monkeypatch.delenv("TEXTIN_SERVER_URL", raising=False)
    server = importlib.reload(importlib.import_module("textin_mcp.server"))

    server._client()

    assert sys.modules["xparse_client"].client_calls == [{}]


def test_client_uses_configured_server_url(monkeypatch):
    install_fake_xparse()
    monkeypatch.setenv("TEXTIN_SERVER_URL", "https://textin.example.test")
    server = importlib.reload(importlib.import_module("textin_mcp.server"))

    server._client()

    assert sys.modules["xparse_client"].client_calls == [
        {"server_url": "https://textin.example.test"}
    ]


def test_parse_run_decodes_base64_content_for_sdk(monkeypatch):
    install_fake_xparse()
    server_module = importlib.reload(importlib.import_module("textin_mcp.server"))
    tool = server_module.create_server()._tool_manager._tools["parse_run"].fn

    result = tool(filename="../sample.pdf", file_base64=base64.b64encode(b"pdf-bytes").decode())

    assert result["markdown"] == "ok"
    assert sys.modules["xparse_client"].parse_calls == [
        (
            "run",
            {
                "filename": "sample.pdf",
                "file_content": b"pdf-bytes",
            },
        )
    ]


def test_parse_create_job_decodes_base64_content_for_sdk(monkeypatch):
    install_fake_xparse()
    server_module = importlib.reload(importlib.import_module("textin_mcp.server"))
    tool = server_module.create_server()._tool_manager._tools["parse_create_job"].fn

    result = tool(
        filename="sample.pdf",
        file_base64=base64.b64encode(b"pdf-bytes").decode(),
        webhook="https://callback.example.test",
    )

    assert result == {"job_id": "job-1"}
    assert sys.modules["xparse_client"].parse_calls == [
        (
            "create_job",
            {
                "filename": "sample.pdf",
                "file_content": b"pdf-bytes",
                "webhook": "https://callback.example.test",
            },
        )
    ]


def test_main_defaults_to_sse_transport():
    from textin_mcp.server import main

    source = inspect.getsource(main)
    assert 'default="sse"' in source


def test_server_host_and_port_can_come_from_environment(monkeypatch):
    from textin_mcp.server import create_server

    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_PORT", "9000")

    server = create_server()

    assert server.settings.host == "0.0.0.0"
    assert server.settings.port == 9000
