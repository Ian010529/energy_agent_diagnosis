from scripts.prepare_m0_env import token


def test_generated_secret_has_cli_safe_prefix() -> None:
    generated = token()

    assert generated.startswith("m0_")
    assert len(generated) >= 32
