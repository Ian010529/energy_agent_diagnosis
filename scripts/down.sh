#!/usr/bin/env bash
set -euo pipefail

env_file="${EDA_ENV_FILE:-.env.example}"
profile="${EDA_PROFILE:-full}"

# 默认保留命名卷，避免普通停止命令误删本地调试数据。
docker compose --env-file "${env_file}" --profile "${profile}" down
