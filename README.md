# TextIn xParse MCP Server

SSE MCP server for TextIn xParse document parsing.

The server exposes the four Python SDK methods documented by TextIn:

- `parse_run`: maps to `client.parse.run()`
- `parse_create_job`: maps to `client.parse.create_job()`
- `parse_get_job`: maps to `client.parse.get_job()`
- `parse_wait_job`: maps to `client.parse.wait_job()`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

Configure authentication with environment variables only:

```powershell
$env:TEXTIN_APP_ID="your-app-id"
$env:TEXTIN_SECRET_CODE="your-secret-code"
```

Do not pass credentials as MCP tool arguments. The server constructs `XParseClient()` without explicit credentials so the official SDK reads its environment variables.

To use a custom TextIn-compatible server address, set `TEXTIN_SERVER_URL`:

```powershell
$env:TEXTIN_SERVER_URL="https://your-server.example.com"
```

When `TEXTIN_SERVER_URL` is unset, the official SDK default server is used.

The MCP tools accept file content as base64. Decoded file size is limited by `MAX_FILE_BYTES`, which defaults to `52428800` bytes.

## Run

```powershell
textin-mcp
```

The default transport is SSE. You can also pass an explicit transport:

```powershell
textin-mcp --transport sse
```

The server listens on `127.0.0.1:8000` by default. Override this for container or remote access:

```powershell
$env:MCP_HOST="0.0.0.0"
$env:MCP_PORT="8000"
textin-mcp --transport sse
```

## Docker

Build the image:

```powershell
docker build -t textin-mcp .
```

Run the SSE MCP server:

```powershell
docker run --rm -p 8000:8000 `
  -e TEXTIN_APP_ID="your-app-id" `
  -e TEXTIN_SECRET_CODE="your-secret-code" `
  -e TEXTIN_SERVER_URL="https://your-server.example.com" `
  -e MAX_FILE_BYTES="52428800" `
  textin-mcp
```

Or run with Docker Compose:

```powershell
docker compose up --build
```

Compose reads `TEXTIN_APP_ID`, `TEXTIN_SECRET_CODE`, optional `TEXTIN_SERVER_URL`, and optional `MAX_FILE_BYTES` from your environment or `.env` file. It starts the MCP SSE service on host port `8000` and the file-to-base64 helper on host port `8005`.

## File to Base64 Helper

The helper is a regular HTTP service, not an MCP SSE endpoint. It accepts a multipart file upload and returns the payload needed by `parse_run` or `parse_create_job`.

Run locally:

```powershell
textin-file-base64
```

By default it listens on `0.0.0.0:8001`. Override with:

```powershell
$env:FILE_BASE64_HOST="0.0.0.0"
$env:FILE_BASE64_PORT="8001"
textin-file-base64
```

Request:

```powershell
curl.exe -X POST "http://127.0.0.1:8005/file-to-base64" `
  -F "file=@D:\docs\example.pdf"
```

Response:

```json
{
  "filename": "example.pdf",
  "mime_type": "application/pdf",
  "size": 12345,
  "base64": "JVBERi0x..."
}
```

## Tools

### `parse_run`

Synchronously parse a local document.

Parameters:

- `filename`: document filename, for example `example.pdf`
- `file_base64`: base64-encoded document content
- `page_range`: optional page range, for example `1-10`
- `password`: optional encrypted PDF password
- `include_hierarchy`
- `include_inline_objects`
- `include_char_details`
- `include_image_data`
- `include_table_structure`
- `pages`
- `title_tree`
- `table_view`: `markdown` or `html`

### `parse_create_job`

Create an asynchronous parsing job.

Parameters:

- `filename`: document filename, for example `example.pdf`
- `file_base64`: base64-encoded document content
- `webhook`: optional completion callback URL
- all parse configuration parameters supported by `parse_run`

### `parse_get_job`

Query an asynchronous parsing job.

Parameters:

- `job_id`

### `parse_wait_job`

Poll until an asynchronous parsing job finishes.

Parameters:

- `job_id`
- `timeout`: default `300.0`
- `poll_interval`: default `5.0`
- `download_result`: when true, downloads `result_url` after completion

## MCP Client Example

```json
{
  "mcpServers": {
    "textin-xparse": {
      "url": "http://127.0.0.1:8000/sse"
    }
  }
}
```

## Reference

- TextIn Python SDK documentation: https://docs.textin.com/xparse/v1/sdk-python
