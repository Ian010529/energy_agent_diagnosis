.PHONY: verify-design lint typecheck test-unit test-contract up-core down-core migrate \
	test-integration-core smoke-foundation smoke-langfuse phase1-check up-phase2 down-phase2 \
	test-unit-phase2 test-contract-phase2 test-integration-phase2 smoke-diagnosis smoke-model \
	smoke-langfuse-diagnosis phase2-check

verify-design:
	git diff --exit-code -- docs/immutable/能源设备运维诊断Agent_详细设计.md

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy

test-unit:
	uv run pytest tests/unit

test-contract:
	uv run pytest tests/contract

up-core:
	docker compose up -d --wait mysql redis

down-core:
	docker compose down

migrate:
	uv run alembic -c migrations/control/alembic.ini upgrade head

test-integration-core:
	uv run pytest -m integration tests/integration/core

smoke-foundation:
	uv run pytest tests/contract/test_health.py tests/unit/test_graph.py

smoke-langfuse:
	uv run python -m energy_agent.observability.smoke

phase1-check: verify-design lint typecheck test-unit test-contract test-integration-core smoke-foundation

up-phase2:
	docker compose up -d --wait mysql redis influxdb

down-phase2:
	docker compose down

test-unit-phase2:
	uv run pytest tests/unit

test-contract-phase2:
	uv run pytest tests/contract

test-integration-phase2:
	uv run pytest -m integration tests/integration/phase2

smoke-diagnosis:
	uv run pytest -m integration tests/integration/phase2/test_diagnosis_smoke.py

smoke-model:
	uv run python -m energy_agent.model.smoke

smoke-langfuse-diagnosis:
	uv run python -m energy_agent.observability.diagnosis_smoke

phase2-check: verify-design lint typecheck phase1-check test-unit-phase2 \
	test-contract-phase2 test-integration-phase2 smoke-diagnosis
