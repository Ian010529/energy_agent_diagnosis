import asyncio
import hashlib
from io import BytesIO

from minio import Minio

from energy_agent.core.errors import (
    MinioChecksumMismatchError,
    MinioUnavailableError,
)


class MinioDocumentProvider:
    provider_type = "minio"

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool,
    ) -> None:
        self.bucket = bucket
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    async def ensure_bucket(self) -> None:
        try:
            exists = await asyncio.to_thread(self.client.bucket_exists, self.bucket)
            if not exists:
                await asyncio.to_thread(self.client.make_bucket, self.bucket)
        except Exception as exc:
            raise MinioUnavailableError("MinIO bucket unavailable") from exc

    async def put_verified(
        self,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: dict[str, str],
    ) -> str:
        checksum = hashlib.sha256(content).hexdigest()
        try:
            await asyncio.to_thread(
                self.client.put_object,
                self.bucket,
                object_key,
                BytesIO(content),
                len(content),
                content_type=content_type,
                metadata={**metadata, "sha256": checksum},
            )
            loaded = await self.get(object_key)
        except MinioUnavailableError:
            raise
        except Exception as exc:
            raise MinioUnavailableError("MinIO upload unavailable") from exc
        if hashlib.sha256(loaded).hexdigest() != checksum:
            raise MinioChecksumMismatchError("MinIO checksum mismatch")
        return checksum

    async def get(self, object_key: str) -> bytes:
        try:
            response = await asyncio.to_thread(self.client.get_object, self.bucket, object_key)
            try:
                return await asyncio.to_thread(response.read)
            finally:
                response.close()
                response.release_conn()
        except Exception as exc:
            raise MinioUnavailableError("MinIO read unavailable") from exc

    async def health(self) -> bool:
        return await asyncio.to_thread(self.client.bucket_exists, self.bucket)
