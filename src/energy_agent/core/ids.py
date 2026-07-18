from uuid import UUID, uuid4


def new_id() -> str:
    return str(uuid4())


def valid_id(value: str | None) -> bool:
    if not value:
        return False
    try:
        UUID(value)
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def trusted_or_new_id(value: str | None) -> str:
    return value if value is not None and valid_id(value) else new_id()
