"""ASGI 服务器使用的默认应用入口。"""

import uvicorn

from energy_agent_diagnosis.app import create_app
from energy_agent_diagnosis.core.config import get_settings

app = create_app()


def run() -> None:
    """使用 EDA 应用配置启动本地单进程服务器。"""
    settings = get_settings()
    uvicorn.run(app, host=settings.app.host, port=settings.app.port)


if __name__ == "__main__":
    run()
