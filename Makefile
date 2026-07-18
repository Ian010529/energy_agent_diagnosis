.PHONY: verify-design lint typecheck test-unit test-contract up-core down-core migrate \
	test-integration-core smoke-foundation smoke-langfuse phase1-check

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
