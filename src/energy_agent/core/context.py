from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class RequestContext:
    trace_id: str
    request_id: str
    session_id: str | None = None
    run_id: str | None = None
    actor_id: str | None = None


_context: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


def bind_context(context: RequestContext) -> Token[RequestContext | None]:
    return _context.set(context)


def get_context() -> RequestContext | None:
    return _context.get()


def context_fields() -> dict[str, str | None]:
    context = get_context()
    return asdict(context) if context else {}


def reset_context(token: Token[RequestContext | None]) -> None:
    _context.reset(token)
