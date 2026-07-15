from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from energy_agent.core.canonicalization import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_digest,
    canonicalize,
)

ROOT = Path(__file__).resolve().parents[2]


def test_committed_cross_language_vectors() -> None:
    vectors = json.loads(
        (ROOT / "tests/fixtures/canonicalization_v2_vectors.json").read_text(encoding="utf-8")
    )
    for vector in vectors:
        encoded = canonicalize(vector["input"])
        assert encoded.decode() == vector["canonical"], vector["name"]
        assert hashlib.sha256(encoded).hexdigest() == vector["sha256"], vector["name"]


def test_decimal_negative_zero_and_no_exponent() -> None:
    assert canonicalize([Decimal("1E+3"), Decimal("1.2300"), Decimal("-0.000")]) == (
        b"[1000,1.23,0]"
    )


def test_nfc_and_nfd_string_values_have_identical_bytes_and_hashes() -> None:
    nfc = "café"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert canonicalize({"value": nfc}) == canonicalize({"value": nfd})
    assert canonical_digest({"value": nfc}) == canonical_digest({"value": nfd})


def test_timezone_is_utc_with_six_microseconds() -> None:
    east_eight = timezone(timedelta(hours=8))
    value = datetime(2026, 7, 15, 12, 30, 1, 42, tzinfo=east_eight)
    assert canonicalize(value) == b'"2026-07-15T04:30:01.000042Z"'
    assert canonical_digest(value) == canonical_digest(value.astimezone(UTC))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_invalid_floats_are_rejected(value: float) -> None:
    with pytest.raises(CanonicalizationError, match="forbidden"):
        canonicalize(value)


def test_naive_datetime_non_string_key_and_nfc_collision_are_rejected() -> None:
    with pytest.raises(CanonicalizationError, match="timezone"):
        canonicalize(datetime(2026, 7, 15))
    with pytest.raises(CanonicalizationError, match="keys must be strings"):
        canonicalize({1: "value"})
    with pytest.raises(CanonicalizationError, match="collide"):
        canonicalize({"é": 1, "e\u0301": 2})


@given(st.dictionaries(st.text(), st.integers(), max_size=20))
def test_mapping_insertion_order_does_not_change_hash(value: dict[str, int]) -> None:
    assert canonical_digest(value) == canonical_digest(dict(reversed(list(value.items()))))


@given(st.text())
def test_business_field_change_changes_hash(value: str) -> None:
    assert canonical_digest({"value": value}) != canonical_digest({"value": value + "!"})


@given(st.text())
def test_string_value_unicode_normalization_is_a_property(value: str) -> None:
    assert canonicalize(value) == canonicalize(unicodedata.normalize("NFC", value))


def test_version_is_frozen_to_two() -> None:
    assert CANONICALIZATION_VERSION == 2
