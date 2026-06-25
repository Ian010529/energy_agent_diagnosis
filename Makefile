UV ?= uv
ENV_FILE ?= .env.example

.PHONY: venv sync run lint format-check typecheck test check compose-config dev-up dev-down infra-up infra-down smoke

venv:
	$(UV) venv --python 3.13.13 .venv

sync:
	$(UV) sync --all-groups --frozen

run:
	$(UV) run --frozen python -m energy_agent_diagnosis.main

lint:
	$(UV) run --frozen ruff check src tests

format-check:
	$(UV) run --frozen ruff format --check src tests

typecheck:
	$(UV) run --frozen mypy src tests

test:
	$(UV) run --frozen pytest

check: lint format-check typecheck test

compose-config:
	docker compose --env-file $(ENV_FILE) --profile dev config --quiet
	docker compose --env-file $(ENV_FILE) --profile full config --quiet

dev-up:
	EDA_ENV_FILE=$(ENV_FILE) EDA_PROFILE=dev ./scripts/up.sh

dev-down:
	EDA_ENV_FILE=$(ENV_FILE) EDA_PROFILE=dev ./scripts/down.sh

infra-up:
	EDA_ENV_FILE=$(ENV_FILE) ./scripts/up.sh

infra-down:
	EDA_ENV_FILE=$(ENV_FILE) ./scripts/down.sh

smoke:
	EDA_ENV_FILE=$(ENV_FILE) ./scripts/smoke.sh
