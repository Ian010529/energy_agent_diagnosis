MAX_TOOL_CALLS_PER_RUN = 8
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_TIMEOUT_SECONDS = 5.0

# Retrieval tools compose several independently bounded operations (query rewrite,
# embedding, vector search and reranking). Their outer timeout must not expire
# before the configured provider timeouts can apply and trigger retrieval's own
# keyword-only degradation.
TOOL_TIMEOUT_SECONDS = {
    "search_manual_chunks": 30.0,
    "search_similar_tickets": 30.0,
}


def timeout_seconds_for(tool_name: str) -> float:
    return TOOL_TIMEOUT_SECONDS.get(tool_name, DEFAULT_TIMEOUT_SECONDS)
