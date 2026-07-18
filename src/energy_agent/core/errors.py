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
