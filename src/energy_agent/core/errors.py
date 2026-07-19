class DomainError(Exception):
    code = "DOMAIN_ERROR"
    retryable = False

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.safe_message = message
        self.details = details or {}


class InvalidStateTransitionError(DomainError):
    code = "INVALID_STATE_TRANSITION"


class ResourceNotFoundError(DomainError):
    code = "RESOURCE_NOT_FOUND"


class DependencyUnavailableError(DomainError):
    code = "DEPENDENCY_UNAVAILABLE"
    retryable = True


class ConflictError(DomainError):
    code = "STATE_CONFLICT"


class AuthenticationError(DomainError):
    code = "AUTHENTICATION_FAILED"


class PermissionDeniedError(DomainError):
    code = "ROLE_FORBIDDEN"


class InvalidRequestError(DomainError):
    code = "INVALID_REQUEST"


class ActorRequiredError(AuthenticationError):
    code = "ACTOR_REQUIRED"


class ActorRoleInvalidError(AuthenticationError):
    code = "ACTOR_ROLE_INVALID"


class SelfReviewForbiddenError(PermissionDeniedError):
    code = "SELF_REVIEW_FORBIDDEN"


class ClarificationStaleError(ConflictError):
    code = "CLARIFICATION_STALE"


class UnknownClarificationQuestionError(InvalidRequestError):
    code = "UNKNOWN_CLARIFICATION_QUESTION"


class ClarificationAlreadyAnsweredError(ConflictError):
    code = "CLARIFICATION_ALREADY_ANSWERED"


class SessionNotReviewableError(ConflictError):
    code = "SESSION_NOT_REVIEWABLE"


class DiagnosisReviewInvalidError(InvalidRequestError):
    code = "DIAGNOSIS_REVIEW_INVALID"


class InvalidEvidenceReferenceError(InvalidRequestError):
    code = "INVALID_EVIDENCE_REFERENCE"


class RootCauseOverrideReasonRequiredError(InvalidRequestError):
    code = "ROOT_CAUSE_OVERRIDE_REASON_REQUIRED"


class CaseNotFoundError(ResourceNotFoundError):
    code = "CASE_NOT_FOUND"


class CaseNotEditableError(ConflictError):
    code = "CASE_NOT_EDITABLE"


class CaseNotReadyError(InvalidRequestError):
    code = "CASE_NOT_READY"


class CaseStateConflictError(ConflictError):
    code = "CASE_STATE_CONFLICT"


class CaseVersionConflictError(ConflictError):
    code = "CASE_VERSION_CONFLICT"


class CaseReviewConflictError(ConflictError):
    code = "CASE_REVIEW_CONFLICT"


class CaseIndexFailedError(DependencyUnavailableError):
    code = "CASE_INDEX_FAILED"


class CaseNotIndexedError(ConflictError):
    code = "CASE_NOT_INDEXED"


class IdempotencyConflictError(ConflictError):
    code = "IDEMPOTENCY_CONFLICT"


class DependencyTimeoutError(DomainError):
    code = "DEPENDENCY_TIMEOUT"
    retryable = True


class UnsupportedIntentError(DomainError):
    code = "UNSUPPORTED_INTENT"


class RagError(DomainError):
    code = "RAG_ERROR"


class DocumentTypeUnsupportedError(RagError):
    code = "DOCUMENT_TYPE_UNSUPPORTED"


class DocumentTooLargeError(RagError):
    code = "DOCUMENT_TOO_LARGE"


class DocumentHashConflictError(ConflictError):
    code = "DOCUMENT_HASH_CONFLICT"


class DocumentParseError(RagError):
    code = "DOCUMENT_PARSE_FAILED"


class OcrRequiredError(DocumentParseError):
    code = "OCR_REQUIRED"


class MinioUnavailableError(DependencyUnavailableError):
    code = "MINIO_UNAVAILABLE"


class MinioChecksumMismatchError(RagError):
    code = "MINIO_CHECKSUM_MISMATCH"


class EmbeddingUnavailableError(DependencyUnavailableError):
    code = "EMBEDDING_UNAVAILABLE"


class EmbeddingDimensionError(RagError):
    code = "EMBEDDING_DIMENSION_INVALID"


class EmbeddingResponseError(RagError):
    code = "EMBEDDING_RESPONSE_INVALID"


class MilvusUnavailableError(DependencyUnavailableError):
    code = "MILVUS_UNAVAILABLE"


class MilvusSchemaMismatchError(RagError):
    code = "MILVUS_SCHEMA_MISMATCH"


class VectorSearchError(DependencyUnavailableError):
    code = "VECTOR_SEARCH_FAILED"


class RerankerUnavailableError(DependencyUnavailableError):
    code = "RERANKER_UNAVAILABLE"


class RerankerResponseError(RagError):
    code = "RERANKER_RESPONSE_INVALID"


class RetrievalChannelsFailedError(DependencyUnavailableError):
    code = "RETRIEVAL_ALL_CHANNELS_FAILED"


class IndexJobNotFoundError(ResourceNotFoundError):
    code = "INDEX_JOB_NOT_FOUND"


class IndexJobStateConflictError(ConflictError):
    code = "INDEX_JOB_STATE_CONFLICT"


class RabbitMQUnavailableError(DependencyUnavailableError):
    code = "RABBITMQ_UNAVAILABLE"


class GraphUnavailableError(DependencyUnavailableError):
    code = "GRAPH_UNAVAILABLE"


class TemplateNotFoundDomainError(InvalidRequestError):
    code = "TEMPLATE_NOT_FOUND"
