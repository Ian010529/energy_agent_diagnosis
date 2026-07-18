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
