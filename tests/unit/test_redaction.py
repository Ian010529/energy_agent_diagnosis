from energy_agent.observability.redaction import ContentMode, redact, safe_snapshot


def test_nested_secrets_are_redacted() -> None:
    value = {
        "authorization": "Bearer secret",
        "nested": [{"password": "pw", "ok": "visible"}],
        "mysql_dsn": "mysql://user:pw@host/db",
    }
    result = redact(value)
    assert result["authorization"] == "[REDACTED]"
    assert result["nested"][0]["password"] == "[REDACTED]"
    assert result["mysql_dsn"] == "[REDACTED]"


def test_metadata_only_hides_raw_content() -> None:
    result = redact({"user_message": "private text"}, mode=ContentMode.METADATA_ONLY)
    assert result["user_message"]["redacted"] is True
    assert "private text" not in repr(result)


def test_string_list_and_depth_limits() -> None:
    result = redact(
        {"long": "x" * 20, "items": list(range(5)), "nested": {"deeper": {"x": 1}}},
        mode=ContentMode.TRUNCATED,
        max_string_length=5,
        max_list_items=2,
        max_depth=2,
    )
    assert result["long"].startswith("xxxxx")
    assert result["items"][-1]["truncated"] is True
    assert result["nested"]["deeper"]["truncated"] is True


def test_snapshot_marks_oversized_data() -> None:
    result = safe_snapshot({"value": "x" * 1000}, max_bytes=100)
    assert result["truncated"] is True
    assert result["original_bytes"] > result["limit_bytes"]
