.PHONY: verify-design lint typecheck test-unit test-contract test-integration test-live \
	test-chaos validate-data load-data evaluate performance package-check \
	prepare-m0-env up-dev up-full up-staging up-production down-full readiness \
	gate-m0 gate-m1 gate-m2 gate-m3 gate-m4 gate-m5 \
	gate-m6 gate-m7 gate-m8 gate-m9 gate-m10 gate-m11

UV := uv

verify-design:
	$(UV) run --no-project python scripts/verify_immutable_design.py

lint:
	$(UV) run ruff check .

typecheck:
	$(UV) run mypy

test-unit:
	$(UV) run pytest tests/unit

test-contract:
	$(UV) run pytest tests/contract

test-integration: gate-m0

test-live: gate-m0

test-chaos: gate-m0

validate-data load-data evaluate performance:
	@echo "$@ belongs to a later module and is not implemented in M0" >&2
	@exit 2

package-check:
	$(UV) build

prepare-m0-env:
	$(UV) run python -m scripts.prepare_m0_env

up-dev: prepare-m0-env
	DEPLOYMENT_PROFILE=dev docker compose --env-file deploy/versions.env --env-file .env.m0 --profile dev up -d --wait

up-full: prepare-m0-env
	$(UV) run --env-file .env.m0 python scripts/validate_profile.py full
	DEPLOYMENT_PROFILE=full docker compose --env-file deploy/versions.env --env-file .env.m0 --profile full up -d --wait

up-staging:
	$(UV) run --env-file .env python scripts/validate_profile.py staging
	$(UV) run --env-file .env python scripts/prepare_milvus_config.py staging
	DEPLOYMENT_PROFILE=staging MILVUS_CONFIG_PATH=./.runtime/milvus-staging.yaml docker compose --env-file deploy/versions.env --env-file .env --profile staging up -d --wait

up-production:
	$(UV) run --env-file .env python scripts/validate_profile.py production
	$(UV) run --env-file .env python scripts/prepare_milvus_config.py production
	DEPLOYMENT_PROFILE=production MILVUS_CONFIG_PATH=./.runtime/milvus-production.yaml docker compose --env-file deploy/versions.env --env-file .env --profile production up -d --wait

down-full:
	docker compose --env-file deploy/versions.env --env-file .env.m0 --profile full down

readiness:
	$(UV) run python -m scripts.m0_gate readiness

gate-m0:
	$(UV) run python -m scripts.m0_gate gate

gate-m1 gate-m2 gate-m3 gate-m4 gate-m5 gate-m6 gate-m7 gate-m8 gate-m9 gate-m10 gate-m11:
	@echo "$@ cannot run while current_module is M0" >&2
	@exit 2
