# The API image: the FastAPI app with only its runtime dependencies (no torch: the
# `ingest` group is left out), as a non-root user. Build from the repository root:
#   docker build -f backend/Dockerfile -t actie-api .
# Base images are pinned by digest, at least two weeks old (supply-chain cooldown):
# python 3.12.14-slim-bookworm (matches .python-version and uv.lock), uv 0.12.19 (as CI).

FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 /uv /bin/uv
# Bytecode compiled once at build time; real copies (the cache is a separate mount);
# the image's own Python, never a downloaded one.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, from the lockfile alone: this layer is reused until uv.lock changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-group ingest --no-install-project
COPY backend ./backend
# The schema and the law snapshot, for the Job that fills an empty database (Lecture 12).
COPY db/schema.sql db/law_snapshot.jsonl.gz ./db/

FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=build --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
# Numeric, not the name: Kubernetes' runAsNonRoot can only verify a number is not 0.
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]
# Exec form: uvicorn is PID 1 and gets SIGTERM, so `docker stop` closes the pools cleanly.
# On SIGTERM it stops taking requests and gives running streams (20-40 s) up to 50 s to
# finish; Kubernetes waits 60 s (terminationGracePeriodSeconds) before killing it.
# Behind nginx the client IP is in X-Forwarded-For; it is trusted from any address because
# only the proxy can reach the API (Compose: no published port; Kubernetes: NetworkPolicy).
CMD ["uvicorn", "backend.app.api:app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "50", "--proxy-headers", "--forwarded-allow-ips", "*"]
