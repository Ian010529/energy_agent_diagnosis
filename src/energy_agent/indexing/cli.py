import argparse
import asyncio
import json

from energy_agent.core.config import Settings
from energy_agent.core.ids import new_id
from energy_agent.indexing.repository import IndexRepository
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory


async def run(args: argparse.Namespace) -> None:
    settings = Settings()
    engine = create_mysql_engine(settings.mysql_dsn)
    repository = IndexRepository(create_session_factory(engine))
    try:
        if args.command == "list-failed":
            print(
                json.dumps(
                    [item.model_dump(mode="json") for item in await repository.failed()],
                    ensure_ascii=False,
                )
            )
        elif args.command == "inspect":
            item = await repository.get(args.job_id)
            if not item:
                raise RuntimeError("INDEX_JOB_NOT_FOUND")
            print(item.model_dump_json())
        elif args.command == "retry":
            item = await repository.retry(args.job_id, new_id())
            if not item:
                raise RuntimeError("INDEX_JOB_STATE_CONFLICT")
            print(item.model_dump_json())
        elif args.command == "health":
            async with engine.connect() as connection:
                await connection.exec_driver_sql("SELECT 1")
            print("INDEX_WORKER_MYSQL=READY")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-failed")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--job-id", required=True)
    retry = commands.add_parser("retry")
    retry.add_argument("--job-id", required=True)
    commands.add_parser("health")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
