import argparse
import asyncio
from pathlib import Path

from energy_agent.core.config import Settings
from energy_agent.core.lifecycle import create_tracer
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.persistence.repositories.manual_document import ManualDocumentRepository
from energy_agent.providers.embedding import OpenAICompatibleEmbeddingProvider
from energy_agent.providers.milvus import MilvusVectorProvider
from energy_agent.providers.minio import MinioDocumentProvider
from energy_agent.retrieval.ingestion.manifests import (
    DocumentManifest,
    ReviewStatus,
)
from energy_agent.retrieval.ingestion.service import DocumentIngestionService


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--device-type", required=True)
    parser.add_argument("--device-model")
    parser.add_argument("--manufacturer")
    parser.add_argument("--alarm-name")
    parser.add_argument("--content-type", default="application/octet-stream")
    parser.add_argument("--approved", action="store_true")
    parser.add_argument("--effective", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    tracer = create_tracer(settings)
    engine = create_mysql_engine(settings.mysql_dsn)
    minio = MinioDocumentProvider(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket=settings.minio_bucket_documents,
        secure=settings.minio_secure,
    )
    embedding = (
        OpenAICompatibleEmbeddingProvider(
            base_url=settings.embedding_base_url or "",
            api_key=settings.embedding_api_key or "",
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            timeout_seconds=settings.embedding_timeout_seconds,
            batch_size=settings.embedding_batch_size,
        )
        if settings.embedding_mode == "openai_compatible"
        else None
    )
    milvus = MilvusVectorProvider(
        uri=settings.milvus_uri,
        token=settings.milvus_token,
        manual_collection=settings.milvus_manual_collection,
        ticket_collection=settings.milvus_ticket_collection,
        dimension=settings.milvus_vector_dimension,
        metric_type=settings.milvus_metric_type,
    )
    try:
        await minio.ensure_bucket()
        await milvus.ensure_collections()
        service = DocumentIngestionService(
            repository=ManualDocumentRepository(create_session_factory(engine)),
            minio=minio,
            milvus=milvus,
            embedding=embedding,
            tracer=tracer,
            max_bytes=settings.document_max_bytes,
        )
        result = await service.ingest(
            DocumentManifest(
                doc_id=args.doc_id,
                document_name=args.path.name,
                version=args.version,
                content_type=args.content_type,
                device_type=args.device_type,
                device_model=args.device_model,
                manufacturer=args.manufacturer,
                alarm_name=args.alarm_name,
                review_status=ReviewStatus.APPROVED if args.approved else ReviewStatus.DRAFT,
                effective=args.effective,
            ),
            args.path.read_bytes(),
        )
        print(result.model_dump_json())
    finally:
        if embedding:
            await embedding.close()
        await milvus.close()
        await engine.dispose()
        await tracer.flush()
        await tracer.shutdown()


if __name__ == "__main__":
    asyncio.run(run())
