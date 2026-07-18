import hashlib
import json


def request_fingerprint(scope: str, payload: object) -> str:
    encoded = json.dumps(
        {"scope": scope, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
