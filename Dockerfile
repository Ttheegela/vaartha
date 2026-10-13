FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY api api
COPY core core
COPY scripts scripts
COPY worker worker
RUN useradd --system --uid 1000 varta && mkdir -p /data/backups && chown -R varta /data
USER varta
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    VARTA_DB_PATH=/data/varta.db VARTA_BACKUP_DIR=/data/backups
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD ["sh", "-c", "python -c \"import urllib.request as u; u.urlopen('http://127.0.0.1:${PORT:-8000}/healthz', timeout=4)\""]
# No --proxy-headers: client IP comes from api/visitor.client_ip, gated by TRUST_PROXY.
CMD ["sh", "-c", "exec uvicorn --factory api.main:create_app --host 0.0.0.0 --port \"${PORT:-8000}\" --no-access-log"]
