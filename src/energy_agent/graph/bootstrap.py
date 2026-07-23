import argparse
import asyncio

from energy_agent.bootstrap.lifespan import create_tracer
from energy_agent.core.config import get_settings
from energy_agent.graph.service import GraphService
from energy_agent.providers.neo4j import Neo4jProvider
from energy_agent.templates.definitions import TEMPLATES


async def run(*, dry_run: bool) -> None:
    settings = get_settings()
    if dry_run:
        for template in TEMPLATES:
            print(f"{template.template_id}@{template.template_version}")
        return
    if settings.graph_mode != "neo4j" or not settings.neo4j_password:
        raise RuntimeError("GRAPH_DISABLED")
    tracer = create_tracer(settings)
    provider = Neo4jProvider(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
        timeout_seconds=settings.neo4j_query_timeout_seconds,
    )
    try:
        await provider.ensure_schema()
        service = GraphService(provider)
        for template in TEMPLATES:
            with tracer.start_span(
                "graph.template.upsert",
                trace_id=f"graph-template-{template.template_id}",
                metadata={
                    "template_id": template.template_id,
                    "template_version": template.template_version,
                    "device_type": template.device_type,
                },
            ):
                await service.bootstrap_template(template)
    finally:
        await provider.close()
        await tracer.flush()
        await tracer.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
