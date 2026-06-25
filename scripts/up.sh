#!/usr/bin/env bash
set -euo pipefail

# 默认使用示例环境文件，允许调用方通过 EDA_ENV_FILE 显式覆盖。
env_file="${EDA_ENV_FILE:-.env.example}"
profile="${EDA_PROFILE:-full}"

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon 未运行，请先启动 Docker Desktop。" >&2
  exit 1
fi

docker compose --env-file "${env_file}" --profile "${profile}" up -d --build
