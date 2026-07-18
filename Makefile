.PHONY: verify-design lint typecheck test-unit test-contract up-core down-core migrate \
	test-integration-core smoke-foundation smoke-langfuse phase1-check up-phase2 down-phase2 \
	test-unit-phase2 test-contract-phase2 test-integration-phase2 smoke-diagnosis smoke-model \
	smoke-langfuse-diagnosis phase2-check \
	up-phase3 down-phase3 test-unit-phase3 test-contract-phase3 \
	test-integration-minio test-integration-milvus test-integration-rag \
	smoke-document-ingest smoke-rag smoke-embedding smoke-reranker \
	smoke-rag-live smoke-langfuse-rag phase3-check

LOCAL_TEST_ENV = RETRIEVAL_MODE=keyword_only QUERY_REWRITE_MODE=rules \
	EMBEDDING_MODE=disabled RERANK_MODE=disabled MODEL_MODE=disabled \
	OBSERVABILITY_MODE=local

verify-design:
	git diff --exit-code -- docs/immutable/能源设备运维诊断Agent_详细设计.md

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
