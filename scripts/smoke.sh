#!/usr/bin/env bash
set -euo pipefail

env_file="${EDA_ENV_FILE:-.env.example}"
base_url="${EDA_SMOKE_BASE_URL:-}"
api_key="${EDA_SMOKE_API_KEY:-}"

# 只读取 smoke 专用键，不 source 整个文件，避免执行不可信配置内容。
if [[ -z "${api_key}" && -f "${env_file}" ]]; then
  api_key="$(awk -F= '$1 == "EDA_SMOKE_API_KEY" {sub(/^[^=]*=/, ""); print; exit}' "${env_file}")"
fi
if [[ -z "${base_url}" && -f "${env_file}" ]]; then
  app_port="$(awk -F= '$1 == "EDA_APP_PORT" {sub(/^[^=]*=/, ""); print; exit}' "${env_file}")"
  base_url="http://127.0.0.1:${app_port:-8000}"
fi
base_url="${base_url:-http://127.0.0.1:8000}"
api_key="${api_key:-replace-local-api-key}"

curl_args=(--fail --silent --show-error --connect-timeout 2 --max-time 5)

# readiness 可能等待多个重型中间件启动，因此按真实墙钟时间预留约五分钟。
deadline=$((SECONDS + 300))
while ((SECONDS < deadline)); do
  # 启动窗口内的连接失败是预期状态；最终校验仍保留详细错误输出。
  if curl "${curl_args[@]}" "${base_url}/health/ready" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

curl "${curl_args[@]}" "${base_url}/health/live" >/dev/null
curl "${curl_args[@]}" "${base_url}/health/ready" >/dev/null
curl "${curl_args[@]}" -H "X-API-Key: ${api_key}" "${base_url}/api/v1/system/ping" >/dev/null
curl "${curl_args[@]}" "${base_url}/metrics" | grep -q "energy_diagnosis_http_requests_total"
echo "阶段 1 smoke test 通过。"
