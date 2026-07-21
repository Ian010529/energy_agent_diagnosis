import json
from pathlib import Path

from energy_agent.app import create_app


def main() -> None:
    target = Path("frontend/openapi/backend.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
