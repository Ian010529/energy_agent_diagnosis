"""验证服务器入口真实使用应用 host/port 配置。"""

import pytest

from energy_agent_diagnosis import main as main_module
from energy_agent_diagnosis.core.config import AppSettings, Settings


def test_run_passes_configured_host_and_port(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(app=AppSettings(host="0.0.0.0", port=8123))
    captured: dict[str, object] = {}

    def fake_run(application: object, *, host: str, port: int) -> None:
        captured.update(application=application, host=host, port=port)

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr("energy_agent_diagnosis.main.uvicorn.run", fake_run)

    main_module.run()

    assert captured == {
        "application": main_module.app,
        "host": "0.0.0.0",
        "port": 8123,
    }
