.PHONY: verify-design architecture-check lint typecheck test-unit test-contract up-core down-core migrate \
	test-integration-core smoke-foundation smoke-langfuse phase1-check up-phase2 down-phase2 \
	test-unit-phase2 test-contract-phase2 test-integration-phase2 smoke-diagnosis smoke-model \
	smoke-langfuse-diagnosis phase2-check \
	up-phase3 down-phase3 test-unit-phase3 test-contract-phase3 \
	test-integration-minio test-integration-milvus test-integration-rag \
	smoke-document-ingest smoke-rag smoke-embedding smoke-reranker \
	smoke-rag-live smoke-langfuse-rag phase3-check \
	up-phase4 down-phase4 test-unit-phase4 test-contract-phase4 \
	test-integration-clarification test-integration-roles test-integration-cases \
	test-integration-case-retrieval smoke-human-clarification smoke-case-lifecycle \
	smoke-case-index smoke-case-retrieval smoke-langfuse-case phase4-check \
	up-phase5 down-phase5 test-unit-phase5 test-contract-phase5 \
	test-integration-rabbitmq test-integration-index-worker test-integration-neo4j \
	test-integration-graph-tool test-integration-scenarios smoke-rabbit-index \
	smoke-index-retry smoke-neo4j smoke-graph-tool smoke-phase5-scenarios \
	smoke-async-case-index smoke-langfuse-worker phase5-check \
	up-phase6 down-phase6 up-pilot-observability down-pilot-observability \
	test-unit-phase6 test-contract-phase6 test-integration-evaluation \
	test-integration-guardrails test-integration-circuit-breakers \
	test-integration-dedup test-integration-sse test-integration-rate-limit \
	test-integration-metrics test-degradation-phase6 test-pilot-stability \
	evaluate-calibration evaluate-regression evaluate-holdout compare-evaluation \
	accept-evaluation-baseline dependency-audit static-security-check docker-build \
	docker-smoke pilot-credentials-check pilot-readiness-report phase6-check pilot-gate \
	reload-pilot-data drain-pilot-index validate-pilot-manual-vectors

.PHONY: backend-dev up-phase7-dev-deps frontend-install frontend-dev frontend-lint frontend-typecheck frontend-test \
	frontend-build frontend-e2e frontend-visual frontend-visual-update openapi-export \
	frontend-generate-client frontend-contract-check test-unit-phase7 test-contract-phase7 \
	test-integration-catalog test-integration-timeline test-integration-evidence \
	test-integration-frontend-api up-phase7 down-phase7 frontend-docker-build \
	frontend-docker-smoke prepare-phase7-e2e-data phase7-check

.PHONY: bootstrap-admin test-unit-auth test-contract-auth test-integration-auth \
	frontend-test-auth frontend-e2e-auth auth-check

.PHONY: module-list module-check

LOCAL_TEST_ENV = APP_ENV=test AUTH_MODE=development_headers INTERNAL_API_KEY= \
	PILOT_MODE=false PILOT_ALLOWED_ACTORS= INDEX_EXECUTION_MODE=sync \
	GRAPH_MODE=disabled RETRIEVAL_MODE=keyword_only QUERY_REWRITE_MODE=rules \
	EMBEDDING_MODE=disabled RERANK_MODE=disabled MODEL_MODE=disabled \
	OBSERVABILITY_MODE=local
AUTH_INTEGRATION_DSN = mysql+aiomysql://energy:energy_dev@localhost:3306/energy_agent_auth_integration
AUTH_E2E_DSN = mysql+aiomysql://energy:energy_dev@localhost:3306/energy_agent_auth_e2e
AUTH_ACCESS_SECRET = auth-access-secret-at-least-thirty-two-bytes
AUTH_REFRESH_SECRET = auth-refresh-secret-at-least-thirty-two-bytes

verify-design:
	git diff --exit-code -- docs/immutable/能源设备运维诊断Agent_详细设计.md

architecture-check:
	uv run python scripts/check_module_boundaries.py

module-list:
	@uv run python scripts/run_module_check.py --list

module-check:
	@test -n "$(MODULE)" || (echo "usage: make module-check MODULE=<module>"; exit 2)
	$(LOCAL_TEST_ENV) uv run python scripts/run_module_check.py "$(MODULE)"

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy

test-unit:
	$(LOCAL_TEST_ENV) uv run pytest tests/unit

test-contract:
	$(LOCAL_TEST_ENV) uv run pytest tests/contract

up-core:
	docker compose up -d --wait mysql redis

down-core:
	docker compose down

migrate:
	uv run alembic -c migrations/control/alembic.ini upgrade head

test-integration-core:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/core

smoke-foundation:
	$(LOCAL_TEST_ENV) uv run pytest tests/contract/test_health.py tests/unit/test_graph.py

smoke-langfuse:
	uv run python -m energy_agent.observability.smoke

phase1-check: verify-design lint typecheck test-unit test-contract test-integration-core smoke-foundation

up-phase2:
	docker compose up -d --wait mysql redis influxdb

down-phase2:
	docker compose down

test-unit-phase2:
	$(LOCAL_TEST_ENV) uv run pytest tests/unit

test-contract-phase2:
	$(LOCAL_TEST_ENV) uv run pytest tests/contract

test-integration-phase2:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase2

smoke-diagnosis:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase2/test_diagnosis_smoke.py

smoke-model:
	uv run python -m energy_agent.model.smoke

smoke-langfuse-diagnosis:
	uv run python -m energy_agent.observability.diagnosis_smoke

phase2-check: verify-design lint typecheck phase1-check test-unit-phase2 \
	test-contract-phase2 test-integration-phase2 smoke-diagnosis

up-phase3:
	docker compose up -d --wait mysql redis influxdb minio etcd milvus

down-phase3:
	docker compose down

test-unit-phase3:
	$(LOCAL_TEST_ENV) uv run pytest tests/unit/test_phase3_rag.py

test-contract-phase3:
	$(LOCAL_TEST_ENV) uv run pytest tests/contract/test_phase3_contracts.py

test-integration-minio:
	uv run pytest -m integration tests/integration/phase3/test_minio.py

test-integration-milvus:
	uv run pytest -m integration tests/integration/phase3/test_milvus.py

test-integration-rag:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase3/test_rag_algorithm.py

smoke-document-ingest:
	uv run pytest -m integration tests/integration/phase3/test_document_ingest.py

smoke-rag:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase3/test_rag_algorithm.py

smoke-embedding:
	uv run python -m energy_agent.retrieval.smoke embedding

smoke-reranker:
	uv run python -m energy_agent.retrieval.smoke reranker

smoke-rag-live:
	uv run python -m energy_agent.retrieval.smoke rag

smoke-langfuse-rag:
	uv run python -m energy_agent.retrieval.smoke langfuse-rag

phase3-check: verify-design lint typecheck phase2-check test-unit-phase3 \
	test-contract-phase3 test-integration-minio test-integration-milvus \
	test-integration-rag smoke-document-ingest smoke-rag

up-phase4:
	docker compose up -d --wait mysql redis influxdb minio etcd milvus

down-phase4:
	docker compose down

test-unit-phase4:
	$(LOCAL_TEST_ENV) uv run pytest tests/unit/test_phase4_human_cases.py

test-contract-phase4:
	$(LOCAL_TEST_ENV) uv run pytest tests/contract/test_phase4_contracts.py

test-integration-clarification:
	$(LOCAL_TEST_ENV) uv run pytest -m integration \
		tests/integration/phase4/test_human_case_lifecycle.py::test_clarification_restore_validation_and_explanation

test-integration-roles:
	$(LOCAL_TEST_ENV) uv run pytest -m integration \
		tests/integration/phase4/test_human_case_lifecycle.py::test_roles_review_case_index_retrieval_disable_and_audit

test-integration-cases:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase4

test-integration-case-retrieval:
	$(LOCAL_TEST_ENV) uv run pytest -m integration \
		tests/integration/phase4/test_human_case_lifecycle.py::test_roles_review_case_index_retrieval_disable_and_audit

smoke-human-clarification: test-integration-clarification

smoke-case-lifecycle: test-integration-cases

smoke-case-index:
	PHASE4_LIVE=1 MODEL_MODE=disabled uv run pytest -m integration \
		tests/integration/phase4/test_human_case_lifecycle.py::test_roles_review_case_index_retrieval_disable_and_audit

smoke-case-retrieval: smoke-case-index

smoke-langfuse-case:
	PHASE4_LIVE=1 MODEL_MODE=disabled uv run pytest -m integration \
		tests/integration/phase4/test_human_case_lifecycle.py::test_roles_review_case_index_retrieval_disable_and_audit

phase4-check: verify-design lint typecheck phase3-check test-unit-phase4 \
	test-contract-phase4 test-integration-clarification test-integration-roles \
	test-integration-cases test-integration-case-retrieval \
	smoke-human-clarification smoke-case-lifecycle

up-phase5:
	docker compose up -d --wait mysql redis influxdb minio etcd milvus rabbitmq neo4j

down-phase5:
	docker compose down

test-unit-phase5:
	$(LOCAL_TEST_ENV) uv run pytest tests/unit/test_phase5_async_graph_scenarios.py

test-contract-phase5:
	$(LOCAL_TEST_ENV) uv run pytest tests/contract/test_phase5_contracts.py

test-integration-rabbitmq:
	uv run pytest -m integration tests/integration/phase5/test_rabbitmq.py

test-integration-index-worker:
	uv run pytest -m integration tests/integration/phase5/test_index_worker.py

test-integration-neo4j:
	uv run pytest -m integration tests/integration/phase5/test_neo4j.py

test-integration-graph-tool:
	uv run pytest -m integration tests/integration/phase5/test_graph_tool.py

test-integration-scenarios:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase5/test_scenarios.py

smoke-rabbit-index: test-integration-index-worker

smoke-index-retry: test-integration-rabbitmq

smoke-neo4j: test-integration-neo4j

smoke-graph-tool: test-integration-graph-tool

smoke-phase5-scenarios: test-integration-scenarios

smoke-async-case-index:
	PHASE5_LIVE=1 uv run pytest -m integration \
		tests/integration/phase5/test_async_index_live.py

smoke-langfuse-worker:
	PHASE5_LIVE=1 OBSERVABILITY_MODE=langfuse uv run pytest -m integration \
		tests/integration/phase5/test_async_index_live.py

phase5-check: verify-design lint typecheck phase4-check test-unit-phase5 \
	test-contract-phase5 test-integration-rabbitmq test-integration-index-worker \
	test-integration-neo4j test-integration-graph-tool test-integration-scenarios

up-phase6:
	docker compose --profile phase6 up -d --wait

down-phase6:
	docker compose --profile phase6 down

up-pilot-observability:
	docker compose --profile pilot-observability up -d

down-pilot-observability:
	docker compose --profile pilot-observability down

test-unit-phase6:
	$(LOCAL_TEST_ENV) uv run pytest tests/unit/test_phase6_hardening.py

test-contract-phase6:
	$(LOCAL_TEST_ENV) uv run pytest tests/contract/test_phase6_contracts.py

test-integration-evaluation:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase6/test_evaluation.py

test-integration-guardrails:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase6/test_guardrails.py

test-integration-circuit-breakers:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase6/test_circuit_breakers.py

test-integration-dedup:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase6/test_dedup.py

test-integration-sse:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase6/test_sse.py

test-integration-rate-limit:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase6/test_rate_limit.py

test-integration-metrics:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase6/test_metrics.py

test-degradation-phase6:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase6/degradation

test-pilot-stability:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase6/test_stability.py

evaluate-calibration:
	uv run python -m energy_agent.evaluation.cli evaluate --split calibration --prepare-runtime

evaluate-regression:
	uv run python -m energy_agent.evaluation.cli evaluate --split regression --prepare-runtime

reload-pilot-data:
	test "$(REPLACE_ALL)" = "1"
	uv run python -m energy_agent.evaluation.reload_dataset --replace-all

drain-pilot-index:
	uv run python -m energy_agent.evaluation.drain_index_queue --batch-size 64

validate-pilot-manual-vectors:
	uv run python -m energy_agent.evaluation.validate_manual_vectors

evaluate-holdout:
	test -n "$(RUN_ID)"
	uv run python -m energy_agent.evaluation.cli evaluate --split holdout \
		--prepare-runtime --run-id "$(RUN_ID)"

compare-evaluation:
	uv run python -m energy_agent.evaluation.cli compare --run-id $(RUN_ID)

accept-evaluation-baseline:
	uv run python -m energy_agent.evaluation.cli accept-baseline --run-id $(RUN_ID)

dependency-audit:
	uv run pip-audit

static-security-check:
	uv run bandit -q -ll -r src
	! git grep -I -nE '(sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH) PRIVATE KEY)' -- \
		src frontend migrations docs deploy .github pyproject.toml compose.yaml Dockerfile .env.example

docker-build:
	docker build -t energy-agent:phase6 .

docker-smoke: docker-build
	docker run --rm energy-agent:phase6 python -c "import energy_agent.app"

pilot-readiness-report:
	test -n "$(RUN_ID)"
	test -f artifacts/pilot-readiness/$(RUN_ID)/evaluation_report.json

pilot-credentials-check:
	uv run python -m energy_agent.pilot_credentials

phase6-check: verify-design lint typecheck phase5-check test-unit-phase6 \
	test-contract-phase6 test-integration-evaluation test-integration-guardrails \
	test-integration-circuit-breakers test-integration-dedup test-integration-sse \
	test-integration-rate-limit test-integration-metrics test-degradation-phase6 \
	dependency-audit static-security-check docker-build docker-smoke \
	evaluate-calibration evaluate-regression

pilot-gate: pilot-credentials-check phase6-check up-phase6 migrate \
	evaluate-holdout pilot-readiness-report

frontend-install:
	cd frontend && pnpm install --frozen-lockfile

up-phase7-dev-deps:
	docker compose up -d --wait mysql redis influxdb minio etcd milvus

backend-dev:
	INDEX_EXECUTION_MODE=sync GRAPH_MODE=disabled uv run uvicorn energy_agent.app:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	set -a; if test -f ./.env; then . ./.env; fi; set +a; \
	export BACKEND_INTERNAL_API_KEY="$${INTERNAL_API_KEY:-}"; \
	export FRONTEND_LOCAL_VIEWER_ACTOR_ID="$${FRONTEND_LOCAL_VIEWER_ACTOR_ID:-local-viewer}"; \
	export FRONTEND_LOCAL_OPERATOR_ACTOR_ID="$${FRONTEND_LOCAL_OPERATOR_ACTOR_ID:-pilot-operator}"; \
	export FRONTEND_LOCAL_REVIEWER_ACTOR_ID="$${FRONTEND_LOCAL_REVIEWER_ACTOR_ID:-pilot-reviewer}"; \
	export FRONTEND_LOCAL_ADMIN_ACTOR_ID="$${FRONTEND_LOCAL_ADMIN_ACTOR_ID:-phase6-evaluator}"; \
	cd frontend && pnpm dev

frontend-lint:
	cd frontend && pnpm lint

frontend-typecheck:
	cd frontend && pnpm typecheck

frontend-test:
	cd frontend && pnpm test

frontend-build:
	cd frontend && pnpm build
	! grep -R -E 'BACKEND_INTERNAL_API_KEY|X-Internal-API-Key' frontend/.next/static

frontend-e2e:
	set -a; if test -f ./.env; then . ./.env; fi; set +a; \
		cd frontend && \
		BACKEND_INTERNAL_API_KEY="$$INTERNAL_API_KEY" \
		FRONTEND_APP_ENV="$${FRONTEND_APP_ENV:-local}" \
		FRONTEND_LOCAL_VIEWER_ACTOR_ID="$${FRONTEND_LOCAL_VIEWER_ACTOR_ID:-local-viewer}" \
		FRONTEND_LOCAL_OPERATOR_ACTOR_ID="$${FRONTEND_LOCAL_OPERATOR_ACTOR_ID:-pilot-operator}" \
		FRONTEND_LOCAL_REVIEWER_ACTOR_ID="$${FRONTEND_LOCAL_REVIEWER_ACTOR_ID:-pilot-reviewer}" \
		FRONTEND_LOCAL_ADMIN_ACTOR_ID="$${FRONTEND_LOCAL_ADMIN_ACTOR_ID:-phase6-evaluator}" \
		PHASE7_REAL_E2E=1 pnpm e2e

prepare-phase7-e2e-data:
	uv run python -m energy_agent.evaluation.reload_dataset --replace-all

frontend-visual:
	cd frontend && pnpm visual

frontend-visual-update:
	cd frontend && pnpm visual:update

openapi-export:
	uv run python -m energy_agent.openapi

frontend-generate-client:
	cd frontend && pnpm generate:api

frontend-contract-check: export LC_ALL := C
frontend-contract-check: export LC_CTYPE := C
frontend-contract-check: export LANG := C
frontend-contract-check:
	set -e; contract_tmp=$$(mktemp -d); trap 'rm -rf "$$contract_tmp"' EXIT; \
		cp frontend/openapi/backend.json $$contract_tmp/backend.json; \
		cp frontend/lib/api/generated.ts $$contract_tmp/generated.ts; \
		$(MAKE) openapi-export frontend-generate-client; \
		diff -u $$contract_tmp/backend.json frontend/openapi/backend.json; \
		diff -u $$contract_tmp/generated.ts frontend/lib/api/generated.ts
	@grep_status=0; \
	/usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C LANG=C /usr/bin/grep -R -E \
		'^(export )?(interface|type) (DiagnosisResponse|StructuredDiagnosisResult|DiagnosisCase|Evidence)([[:space:]=]|$$)' \
		frontend/app frontend/components frontend/lib --exclude=generated.ts --exclude=types.ts \
		|| grep_status=$$?; \
	if [ $$grep_status -eq 0 ]; then \
		echo "duplicate frontend DTO declaration found"; exit 1; \
	elif [ $$grep_status -ne 1 ]; then \
		echo "frontend DTO scan failed with status $$grep_status"; exit $$grep_status; \
	fi

test-unit-phase7:
	$(LOCAL_TEST_ENV) uv run pytest tests/unit/test_phase7_frontend_api.py

test-contract-phase7:
	$(LOCAL_TEST_ENV) uv run pytest tests/contract/test_phase7_contracts.py

test-integration-catalog:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase7/test_frontend_api.py -k catalog

test-integration-timeline:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase7/test_frontend_api.py -k timeline

test-integration-evidence:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase7/test_frontend_api.py -k evidence

test-integration-frontend-api:
	$(LOCAL_TEST_ENV) uv run pytest -m integration tests/integration/phase7

up-phase7:
	docker compose --profile phase7 up -d --wait

down-phase7:
	docker compose --profile phase7 down

frontend-docker-build:
	docker build -t energy-agent-frontend:phase7 frontend

frontend-docker-smoke: frontend-docker-build
	docker run --rm energy-agent-frontend:phase7 node -e "require('./server.js')" & \
		container_pid=$$!; sleep 3; kill $$container_pid

phase7-check: verify-design architecture-check up-phase7 migrate phase6-check test-unit-phase7 test-contract-phase7 \
	test-integration-frontend-api frontend-contract-check frontend-lint frontend-typecheck \
	frontend-test frontend-build prepare-phase7-e2e-data frontend-e2e frontend-visual \
	frontend-docker-smoke

bootstrap-admin:
	uv run python -m energy_agent.users.cli bootstrap-admin

test-unit-auth:
	$(LOCAL_TEST_ENV) uv run pytest tests/unit/test_phase7_5_auth.py

test-contract-auth:
	$(LOCAL_TEST_ENV) uv run pytest tests/contract/test_phase7_5_auth_contracts.py

test-integration-auth: up-core
	@set -e; \
		auth_db=energy_agent_auth_integration; \
		cleanup() { \
			docker compose exec -T mysql mysql -uroot -proot_dev \
				-e "DROP DATABASE IF EXISTS $$auth_db" >/dev/null; \
			docker compose exec -T redis redis-cli -n 14 FLUSHDB >/dev/null; \
		}; \
		trap cleanup EXIT; \
		cleanup; \
		docker compose exec -T mysql mysql -uroot -proot_dev \
			-e "CREATE DATABASE $$auth_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL PRIVILEGES ON $$auth_db.* TO 'energy'@'%';"; \
		MYSQL_DSN="$(AUTH_INTEGRATION_DSN)" \
			uv run alembic -c migrations/control/alembic.ini upgrade head; \
		APP_ENV=test AUTH_MODE=jwt INTERNAL_API_KEY=auth-integration-key \
		MYSQL_DSN="$(AUTH_INTEGRATION_DSN)" REDIS_URL=redis://localhost:6379/14 \
		JWT_ACCESS_SECRET="$(AUTH_ACCESS_SECRET)" JWT_REFRESH_SECRET="$(AUTH_REFRESH_SECRET)" \
		PILOT_MODE=false RATE_LIMIT_ENABLED=true INDEX_EXECUTION_MODE=sync GRAPH_MODE=disabled \
		RETRIEVAL_MODE=keyword_only QUERY_REWRITE_MODE=rules EMBEDDING_MODE=disabled \
		RERANK_MODE=disabled MODEL_MODE=disabled OBSERVABILITY_MODE=local \
		uv run pytest -m integration tests/integration/auth

frontend-test-auth:
	cd frontend && pnpm test -- tests/unit/auth.test.tsx

frontend-e2e-auth: up-core
	@set -e; \
		auth_db=energy_agent_auth_e2e; \
		cleanup() { \
			docker compose exec -T mysql mysql -uroot -proot_dev \
				-e "DROP DATABASE IF EXISTS $$auth_db" >/dev/null; \
			docker compose exec -T redis redis-cli -n 15 FLUSHDB >/dev/null; \
		}; \
		trap cleanup EXIT; \
		cleanup; \
		docker compose exec -T mysql mysql -uroot -proot_dev \
			-e "CREATE DATABASE $$auth_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL PRIVILEGES ON $$auth_db.* TO 'energy'@'%';"; \
		MYSQL_DSN="$(AUTH_E2E_DSN)" \
			uv run alembic -c migrations/control/alembic.ini upgrade head; \
		APP_ENV=test AUTH_MODE=jwt MYSQL_DSN="$(AUTH_E2E_DSN)" \
		JWT_ACCESS_SECRET="$(AUTH_ACCESS_SECRET)" JWT_REFRESH_SECRET="$(AUTH_REFRESH_SECRET)" \
		BOOTSTRAP_ADMIN_USERNAME=e2e-admin \
		BOOTSTRAP_ADMIN_PASSWORD=e2e-admin-password-1 \
		BOOTSTRAP_ADMIN_DISPLAY_NAME="E2E Admin" \
			uv run python -m energy_agent.users.cli bootstrap-admin; \
		uv run python /Users/chl/.codex/skills/webapp-testing/scripts/with_server.py --timeout 60 \
			--server "APP_ENV=test AUTH_MODE=jwt INTERNAL_API_KEY=auth-e2e-key MYSQL_DSN=$(AUTH_E2E_DSN) REDIS_URL=redis://localhost:6379/15 JWT_ACCESS_SECRET=$(AUTH_ACCESS_SECRET) JWT_REFRESH_SECRET=$(AUTH_REFRESH_SECRET) PILOT_MODE=false RATE_LIMIT_ENABLED=true RATE_LIMIT_AUTH_LOGIN_USERNAME=50 RATE_LIMIT_AUTH_LOGIN_SOURCE=100 RATE_LIMIT_AUTH_REFRESH_PER_MINUTE=100 LOG_LEVEL=WARNING INDEX_EXECUTION_MODE=sync GRAPH_MODE=disabled RETRIEVAL_MODE=keyword_only QUERY_REWRITE_MODE=rules EMBEDDING_MODE=disabled RERANK_MODE=disabled MODEL_MODE=disabled OBSERVABILITY_MODE=local uv run uvicorn energy_agent.app:app --host 127.0.0.1 --port 8000 --log-level warning" --port 8000 \
			--server "cd frontend && BACKEND_BASE_URL=http://127.0.0.1:8000 BACKEND_INTERNAL_API_KEY=auth-e2e-key FRONTEND_AUTH_MODE=jwt AUTH_COOKIE_SECURE=false pnpm dev" --port 3000 \
			-- zsh -lc "cd frontend && PHASE75_REAL_E2E=1 pnpm exec playwright test tests/e2e/auth.spec.ts --project=chromium --workers=1"

auth-check: verify-design architecture-check lint typecheck test-unit-auth test-contract-auth \
	test-integration-auth openapi-export frontend-generate-client frontend-lint \
	frontend-typecheck frontend-test-auth frontend-e2e-auth docker-smoke \
	frontend-docker-smoke
