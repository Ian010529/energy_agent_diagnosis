import unicodedata

from pwdlib import PasswordHash

from energy_agent.core.errors import AuthNewPasswordInvalidError

_PASSWORD_HASH = PasswordHash.recommended()
_DUMMY_HASH = _PASSWORD_HASH.hash("energy-agent-dummy-password-not-a-user")


def normalize_username(username: str) -> str:
    return unicodedata.normalize("NFKC", username.strip()).casefold()


def validate_password(password: str, username: str) -> None:
    if not password.strip() or not 10 <= len(password) <= 128:
        raise AuthNewPasswordInvalidError("Password must contain 10 to 128 characters")
    if normalize_username(password) == normalize_username(username):
        raise AuthNewPasswordInvalidError("Password must not equal username")


def hash_password(password: str, username: str) -> str:
    validate_password(password, username)
    return _PASSWORD_HASH.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _PASSWORD_HASH.verify(password, password_hash)
    except Exception:
        return False


def dummy_verify(password: str) -> None:
    verify_password(password, _DUMMY_HASH)
