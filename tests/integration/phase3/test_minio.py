import hashlib
import uuid

import pytest

from energy_agent.core.errors import MinioUnavailableError
from energy_agent.providers.minio import MinioDocumentProvider

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_real_minio_upload_read_checksum_and_unavailable_mapping() -> None:
    provider = MinioDocumentProvider(
        endpoint="localhost:9000",
        access_key="energy",
        secret_key="energy_minio_dev",
        bucket="energy-documents-test",
        secure=False,
    )
    await provider.ensure_bucket()
    content = "PCS 温度告警维护手册".encode()
    key = f"integration/{uuid.uuid4()}/manual.md"
    checksum = await provider.put_verified(
        key,
        content,
        "text/markdown",
        {"document-id": "DOC-INTEGRATION", "version": "1.0"},
    )
    assert await provider.get(key) == content
    assert checksum == hashlib.sha256(content).hexdigest()
    unavailable = MinioDocumentProvider(
        endpoint="127.0.0.1:1",
        access_key="x",
        secret_key="y",
        bucket="missing",
        secure=False,
    )
    with pytest.raises(MinioUnavailableError):
        await unavailable.get("missing")
