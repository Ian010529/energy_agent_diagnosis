from energy_agent.agent.state import Evidence
from energy_agent.core.errors import (
    DocumentHashConflictError,
    EmbeddingDimensionError,
    MilvusSchemaMismatchError,
    OcrRequiredError,
    RerankerResponseError,
)
from energy_agent.retrieval.contracts import (
    EvidencePackage,
    QueryRewrite,
    RankedEvidence,
    RetrievalCandidate,
    RetrievalMetadata,
    RetrievalResult,
)
from energy_agent.tools.contracts import (
    ManualSearchFilters,
    ManualSearchInput,
    TicketSearchFilters,
    TicketSearchInput,
)


def test_phase3_contracts_are_strict_and_public_tool_names_remain_stable() -> None:
    schemas = (
        QueryRewrite,
        RetrievalCandidate,
        RankedEvidence,
        RetrievalMetadata,
        RetrievalResult,
        EvidencePackage,
        ManualSearchFilters,
        TicketSearchFilters,
        ManualSearchInput,
        TicketSearchInput,
    )
    assert all(schema.model_json_schema()["additionalProperties"] is False for schema in schemas)
    assert ManualSearchInput.model_json_schema()["properties"]["retrieval_mode"]["default"] == (
        "hybrid"
    )
    assert TicketSearchInput.model_json_schema()["properties"]["verified_only"]["default"] is True


def test_evidence_keeps_phase2_fields_and_adds_explainable_scores() -> None:
    properties = Evidence.model_json_schema()["properties"]
    assert {"reliability", "relevance"} <= properties.keys()
    assert {
        "retrieval_score",
        "source_reliability",
        "verification_score",
        "freshness_score",
        "relevance_to_alarm",
        "final_score",
        "chunk_id",
        "package_id",
    } <= properties.keys()


def test_phase3_error_codes_are_stable() -> None:
    assert OcrRequiredError.code == "OCR_REQUIRED"
    assert DocumentHashConflictError.code == "DOCUMENT_HASH_CONFLICT"
    assert EmbeddingDimensionError.code == "EMBEDDING_DIMENSION_INVALID"
    assert MilvusSchemaMismatchError.code == "MILVUS_SCHEMA_MISMATCH"
    assert RerankerResponseError.code == "RERANKER_RESPONSE_INVALID"
