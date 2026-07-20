from energy_agent.core.config import Settings


def missing_pilot_configuration(settings: Settings) -> list[str]:
    missing: list[str] = []
    if settings.auth_mode != "trusted_headers":
        missing.append("AUTH_MODE=trusted_headers")
    if not settings.internal_api_key:
        missing.append("INTERNAL_API_KEY")
    if not settings.pilot_mode:
        missing.append("PILOT_MODE=true")
    if not settings.pilot_allowed_actors.strip():
        missing.append("PILOT_ALLOWED_ACTORS")
    if settings.retrieval_mode != "hybrid":
        missing.append("RETRIEVAL_MODE=hybrid")
    if settings.embedding_mode != "openai_compatible":
        missing.append("EMBEDDING_MODE=openai_compatible")
    if not settings.embedding_base_url:
        missing.append("EMBEDDING_BASE_URL")
    if not settings.embedding_api_key:
        missing.append("EMBEDDING_API_KEY")
    if settings.rerank_mode != "http":
        missing.append("RERANK_MODE=http")
    if not settings.rerank_base_url:
        missing.append("RERANK_BASE_URL")
    if not settings.rerank_api_key:
        missing.append("RERANK_API_KEY")
    if settings.observability_mode != "langfuse":
        missing.append("OBSERVABILITY_MODE=langfuse")
    if not settings.langfuse_public_key:
        missing.append("LANGFUSE_PUBLIC_KEY")
    if not settings.langfuse_secret_key:
        missing.append("LANGFUSE_SECRET_KEY")
    if settings.model_mode == "openai":
        if not settings.openai_api_key:
            missing.append("OPENAI_API_KEY")
    elif settings.model_mode == "openai_compatible":
        if not settings.model_gateway_base_url:
            missing.append("MODEL_GATEWAY_BASE_URL")
        if not settings.model_gateway_api_key:
            missing.append("MODEL_GATEWAY_API_KEY")
    else:
        missing.append("MODEL_MODE=openai|openai_compatible")
    return missing


def main() -> None:
    missing = missing_pilot_configuration(Settings())
    if missing:
        print(f"BLOCKED_MISSING_CREDENTIALS: {' '.join(missing)}")
        raise SystemExit(1)
    print("PILOT_CREDENTIALS_CONFIGURED")


if __name__ == "__main__":
    main()
