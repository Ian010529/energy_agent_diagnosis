from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "energy_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
AUTH_ATTEMPTS = Counter("energy_auth_attempts_total", "Authentication attempts", ["outcome"])
AUTH_REFRESH = Counter("energy_auth_refresh_total", "Refresh attempts", ["outcome"])
AUTH_SESSIONS_REVOKED = Counter(
    "energy_auth_sessions_revoked_total", "Revoked authentication sessions", ["reason_category"]
)
USER_ADMIN_ACTIONS = Counter(
    "energy_user_admin_actions_total", "Administrative user actions", ["action", "outcome"]
)
HTTP_DURATION = Histogram(
    "energy_http_request_duration_seconds", "HTTP request duration", ["method", "route"]
)
RATE_LIMIT_REJECTIONS = Counter(
    "energy_rate_limit_rejections_total", "Rate limit rejections", ["group"]
)

DIAGNOSIS_RUNS = Counter("energy_diagnosis_runs_total", "Diagnosis runs", ["template", "status"])
DIAGNOSIS_DURATION = Histogram(
    "energy_diagnosis_duration_seconds", "Diagnosis duration", ["template"]
)
FIRST_EVENT_LATENCY = Histogram(
    "energy_first_event_latency_seconds", "First SSE event latency", ["template"]
)
DIAGNOSIS_PHASE = Counter("energy_diagnosis_phase_total", "Diagnosis phase transitions", ["phase"])
SESSION_FAILURES = Counter("energy_session_failures_total", "Session failures", ["category"])
HUMAN_ESCALATIONS = Counter("energy_human_escalations_total", "Human escalations", ["reason"])
ALARM_DEDUP = Counter("energy_alarm_dedup_total", "Alarm dedup outcomes", ["outcome"])

NODE_DURATION = Histogram(
    "energy_agent_node_duration_seconds", "Agent node duration", ["node", "status"]
)
NODE_TOTAL = Counter("energy_agent_node_total", "Agent nodes", ["node", "status"])
TOOL_CALLS = Counter("energy_tool_calls_total", "Tool attempts", ["tool", "status"])
TOOL_DURATION = Histogram("energy_tool_duration_seconds", "Tool duration", ["tool", "status"])

MODEL_CALLS = Counter("energy_model_calls_total", "Model calls", ["provider", "status"])
MODEL_DURATION = Histogram(
    "energy_model_duration_seconds", "Model duration", ["provider", "status"]
)
MODEL_TOKENS = Counter("energy_model_tokens_total", "Model tokens", ["provider", "direction"])
RETRIEVAL_QUERIES = Counter(
    "energy_retrieval_queries_total", "Retrieval queries", ["mode", "status"]
)
RETRIEVAL_DURATION = Histogram("energy_retrieval_duration_seconds", "Retrieval duration", ["mode"])
RETRIEVAL_EVIDENCE = Histogram(
    "energy_retrieval_evidence_count", "Retrieved evidence", ["source_type"]
)
RETRIEVAL_DEGRADED = Counter(
    "energy_retrieval_degraded_total", "Retrieval degradation", ["component"]
)

HUMAN_REVIEWS = Counter("energy_human_reviews_total", "Human reviews", ["decision"])
CASE_TRANSITIONS = Counter(
    "energy_case_transitions_total", "Case transitions", ["from_status", "to_status"]
)
CASE_INDEX_STATUS = Counter("energy_case_index_status_total", "Case index status", ["status"])

INDEX_JOBS = Counter("energy_index_jobs_total", "Index jobs", ["status"])
INDEX_JOB_DURATION = Histogram(
    "energy_index_job_duration_seconds", "Index job duration", ["entity_type", "status"]
)
INDEX_RETRIES = Counter("energy_index_retries_total", "Index retries", ["entity_type"])
INDEX_DEAD_LETTERS = Counter(
    "energy_index_dead_letters_total", "Index dead letters", ["entity_type"]
)
OUTBOX_PUBLISH = Counter("energy_outbox_publish_total", "Outbox publishes", ["status"])
GRAPH_PROJECTION = Counter("energy_graph_projection_total", "Graph projections", ["status"])

CIRCUIT_BREAKER_STATE = Gauge(
    "energy_circuit_breaker_state",
    "Circuit state (closed=0, half-open=0.5, open=1)",
    ["dependency"],
)
GUARDRAIL_DECISIONS = Counter(
    "energy_guardrail_decisions_total", "Guardrail decisions", ["layer", "status"]
)
HIGH_RISK_ACTIONS = Counter("energy_high_risk_actions_total", "High risk actions", ["confirmation"])
UNSUPPORTED_CLAIMS = Counter("energy_unsupported_claims_total", "Unsupported claims", ["reason"])


def normalized_route(path: str) -> str:
    if path.startswith("/api/v1/diagnosis/sessions/"):
        return "/api/v1/diagnosis/sessions/{id}"
    if path.startswith("/api/v1/cases/"):
        return "/api/v1/cases/{id}"
    return path
