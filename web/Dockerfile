# Build context is the repo root (see docker-compose.yml's `context: ..`) --
# this image needs both folk-the-library (../folk, ../pyproject.toml) and
# this subtree's own dependency manifest. folk's own pyproject.toml gains no
# dependency from this (CLAUDE.md invariant 8): `pip install .` installs the
# stdlib-only folk package; web/requirements.txt is installed as a fully
# separate step, for this image only.
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./pyproject.toml
COPY folk/ ./folk/
COPY web/requirements.txt ./web/requirements.txt

RUN pip install uv && \
    uv pip install --system . && \
    uv pip install --system -r web/requirements.txt

COPY web/ ./web/

WORKDIR /app/web
