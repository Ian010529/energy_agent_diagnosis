from energy_agent.app import create_app


def test_auth_and_admin_user_paths_are_exported() -> None:
    paths = create_app().openapi()["paths"]
    required = {
        "/api/v1/auth/login": {"post"},
        "/api/v1/auth/refresh": {"post"},
        "/api/v1/auth/me": {"get"},
        "/api/v1/auth/change-password": {"post"},
        "/api/v1/auth/logout": {"post"},
        "/api/v1/auth/logout-all": {"post"},
        "/api/v1/users": {"get", "post"},
        "/api/v1/users/{user_id}": {"get", "patch"},
        "/api/v1/users/{user_id}/disable": {"post"},
        "/api/v1/users/{user_id}/enable": {"post"},
        "/api/v1/users/{user_id}/reset-password": {"post"},
        "/api/v1/users/{user_id}/revoke-sessions": {"post"},
    }
    for path, methods in required.items():
        assert path in paths
        assert methods <= set(paths[path])


def test_user_contract_is_single_role_and_never_exposes_secrets() -> None:
    schema = create_app().openapi()
    profile = schema["components"]["schemas"]["UserProfile"]["properties"]
    assert "role" in profile
    assert "roles" not in profile
    serialized = str(schema).lower()
    for forbidden in ("password_hash", "token_hash", "refresh_token_hash"):
        assert forbidden not in serialized
    assert "/api/v1/auth/register" not in schema["paths"]
