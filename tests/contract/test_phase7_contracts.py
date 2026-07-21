from energy_agent.app import create_app


def test_phase7_openapi_paths_and_existing_diagnosis_protocol() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]
    required = {
        "/api/v1/capabilities": {"get"},
        "/api/v1/sites": {"get"},
        "/api/v1/devices": {"get"},
        "/api/v1/devices/{device_id}": {"get"},
        "/api/v1/alarms": {"get"},
        "/api/v1/alarms/{alarm_id}": {"get"},
        "/api/v1/diagnosis/sessions": {"get", "post"},
        "/api/v1/diagnosis/sessions/{session_id}/timeline": {"get"},
        "/api/v1/diagnosis/sessions/{session_id}/evidence/{evidence_id}": {"get"},
        "/api/v1/diagnosis/sessions/{session_id}/timeseries": {"get"},
        "/api/v1/diagnosis/sessions/{session_id}/messages/stream": {"post"},
        "/api/v1/cases": {"get"},
    }
    for path, methods in required.items():
        assert path in paths
        assert methods <= set(paths[path])


def test_phase7_contracts_do_not_expose_server_secrets_or_gold() -> None:
    serialized = str(create_app().openapi()).lower()
    for forbidden in (
        "backend_internal_api_key",
        "internal_api_key",
        "openai_api_key",
        "mysql_dsn",
        "gold_root_cause",
    ):
        assert forbidden not in serialized


def test_case_pagination_is_additive() -> None:
    schema = create_app().openapi()
    response = schema["components"]["schemas"]["CaseListResponse"]
    properties = response["properties"]
    assert {"items", "total", "next_cursor", "has_more"} <= set(properties)


def test_evidence_and_timeseries_contracts_are_session_scoped() -> None:
    schema = create_app().openapi()
    evidence = schema["components"]["schemas"]["EvidenceDetail"]["properties"]
    assert {
        "evidence_id",
        "source_type",
        "source_id",
        "citation",
        "verified",
        "scores",
        "metadata",
    } <= set(evidence)

    timeseries_path = schema["paths"]["/api/v1/diagnosis/sessions/{session_id}/timeseries"]["get"]
    parameters = {item["name"] for item in timeseries_path["parameters"]}
    assert {"session_id", "run_id", "metric", "start_time", "end_time"} <= parameters
    series = schema["components"]["schemas"]["TimeseriesSeries"]["properties"]
    point = schema["components"]["schemas"]["TimeseriesPoint"]["properties"]
    assert {"metric", "unit", "points"} <= set(series)
    assert {"timestamp", "value", "quality"} <= set(point)


def test_capabilities_publish_exactly_the_registered_five_templates() -> None:
    from energy_agent.agent.templates.routing import DEFAULT_TEMPLATE_REGISTRY
    from energy_agent.catalog.service import CatalogService

    assert len(DEFAULT_TEMPLATE_REGISTRY.templates) == 5
    assert CatalogService.capabilities.__annotations__["return"].__name__ == (
        "CapabilitiesResponse"
    )
