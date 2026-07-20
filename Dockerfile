FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

RUN groupadd --system energy && useradd --system --gid energy --home-dir /app energy \
    && chown -R energy:energy /app
USER energy

EXPOSE 8000
CMD ["uvicorn", "energy_agent.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
