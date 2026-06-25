# uv 只负责可重复安装，运行镜像仍使用官方 Python 基础镜像。
FROM ghcr.io/astral-sh/uv:0.11.8 AS uv

FROM python:3.13.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# 生产镜像不安装开发依赖，依赖版本完全来自 uv.lock。
RUN uv sync --frozen --no-dev && \
    groupadd --system app && useradd --system --gid app app && \
    chown -R app:app /app

USER app

EXPOSE 8000

CMD [".venv/bin/uvicorn", "energy_agent_diagnosis.main:app", "--host", "0.0.0.0", "--port", "8000"]
