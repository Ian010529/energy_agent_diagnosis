import hashlib
import re
import unicodedata


def normalize_alarm_category(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\s_/\\-]+", "", normalized)


def alarm_dedup_key(device_id: str, alarm_category: str) -> str:
    payload = f"{device_id}\x00{normalize_alarm_category(alarm_category)}"
    return hashlib.sha256(payload.encode()).hexdigest()
