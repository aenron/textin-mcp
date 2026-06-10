FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    FILE_BASE64_HOST=0.0.0.0 \
    FILE_BASE64_PORT=8001

WORKDIR /app

COPY pyproject.toml requirements.txt ./
COPY src ./src

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e .

EXPOSE 8000 8001

CMD ["textin-mcp", "--transport", "sse"]
