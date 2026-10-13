# syntax=docker/dockerfile:1

# --------------------------------------------------------------------------
# Stage 1: builder - resolve dependencies into an isolated virtual environment
# --------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install -r requirements.txt

# --------------------------------------------------------------------------
# Stage 2: runtime - slim production image, no build tooling, non-root user
# --------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    ACEEST_DB_PATH=/data/aceest_fitness.db

RUN useradd --create-home --uid 10001 aceest && \
    mkdir -p /data && chown aceest:aceest /data

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=aceest:aceest app.py fitness.py models.py ./
COPY --chown=aceest:aceest templates ./templates
COPY --chown=aceest:aceest static ./static

USER aceest
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3).status == 200 else 1)"

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "60", "app:create_app()"]

# --------------------------------------------------------------------------
# Stage 3: test - adds the Pytest tooling used by CI quality gates only
# --------------------------------------------------------------------------
FROM runtime AS test

USER root
COPY requirements-dev.txt requirements.txt ./
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements-dev.txt
COPY --chown=aceest:aceest pytest.ini .flake8 ./
COPY --chown=aceest:aceest tests ./tests

USER aceest
ENV ACEEST_DB_PATH=/tmp/aceest_test.db
CMD ["pytest", "-v"]
