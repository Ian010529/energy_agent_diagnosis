import asyncio
import json
from typing import Any

from pymilvus import DataType, MilvusClient

from energy_agent.core.errors import MilvusSchemaMismatchError, MilvusUnavailableError


class MilvusVectorProvider:
    provider_type = "milvus"

    def __init__(
        self,
        *,
        uri: str,
        token: str | None,
        manual_collection: str,
        ticket_collection: str,
        dimension: int,
        metric_type: str,
        case_collection: str = "reviewed_cases",
    ) -> None:
        self.manual_collection = manual_collection
        self.ticket_collection = ticket_collection
        self.case_collection = case_collection
        self.collections = {
            "manual": manual_collection,
            "ticket": ticket_collection,
            "case": case_collection,
        }
        self.dimension = dimension
        self.metric_type = metric_type
        try:
            self.client = MilvusClient(uri=uri, token=token or "")
        except Exception as exc:
            raise MilvusUnavailableError("Milvus connection unavailable") from exc

    def _ensure_collection_sync(self, name: str, *, source: str) -> None:
        if self.client.has_collection(name):
            description = self.client.describe_collection(name)
            vector = next(
                (field for field in description["fields"] if field["name"] == "embedding"),
                None,
            )
            if not vector or int(vector["params"]["dim"]) != self.dimension:
                raise MilvusSchemaMismatchError(f"Collection {name} dimension mismatch")
            return
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(
            field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=128
        )
        for field in (
            ("source_id", 128),
            ("device_type", 64),
            ("device_model", 128),
            ("manufacturer", 128),
            ("alarm_name", 255),
            ("index_generation", 64),
        ):
            schema.add_field(field_name=field[0], datatype=DataType.VARCHAR, max_length=field[1])
        schema.add_field(field_name="verified", datatype=DataType.BOOL)
        schema.add_field(field_name="effective", datatype=DataType.BOOL)
        if source == "ticket":
            schema.add_field(field_name="close_time", datatype=DataType.INT64)
        if source == "case":
            schema.add_field(field_name="case_version", datatype=DataType.INT64)
        schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=self.dimension)
        index = self.client.prepare_index_params()
        index.add_index(
            field_name="embedding",
            index_type="AUTOINDEX",
            metric_type=self.metric_type,
        )
        self.client.create_collection(name, schema=schema, index_params=index)

    async def ensure_collections(self) -> None:
        try:
            await asyncio.to_thread(
                self._ensure_collection_sync, self.manual_collection, source="manual"
            )
            await asyncio.to_thread(
                self._ensure_collection_sync, self.ticket_collection, source="ticket"
            )
            await asyncio.to_thread(
                self._ensure_collection_sync, self.case_collection, source="case"
            )
        except MilvusSchemaMismatchError:
            raise
        except Exception as exc:
            raise MilvusUnavailableError("Milvus collection unavailable") from exc

    async def upsert(self, source: str, rows: list[dict[str, Any]]) -> None:
        collection = self.collections[source]
        try:
            await asyncio.to_thread(self.client.upsert, collection, data=rows)
            await asyncio.to_thread(self.client.flush, collection)
        except Exception as exc:
            raise MilvusUnavailableError("Milvus upsert unavailable") from exc

    async def search(
        self,
        source: str,
        vector: list[float],
        allowed_ids: list[str],
        limit: int,
    ) -> list[dict[str, object]]:
        if len(vector) != self.dimension:
            raise MilvusSchemaMismatchError("Query vector dimension mismatch")
        if not allowed_ids:
            return []
        collection = self.collections[source]
        escaped = json.dumps(allowed_ids, ensure_ascii=False)
        try:
            result = await asyncio.to_thread(
                self.client.search,
                collection,
                data=[vector],
                filter=f"id in {escaped}",
                limit=limit,
                output_fields=["source_id", "embedding"],
                search_params={"metric_type": self.metric_type},
            )
            return [
                {
                    "id": hit["id"],
                    "source_id": hit["entity"]["source_id"],
                    "vector_score": max(0.0, min(1.0, float(hit["distance"]))),
                    "embedding": hit["entity"].get("embedding"),
                }
                for hit in result[0]
            ]
        except Exception as exc:
            raise MilvusUnavailableError("Milvus vector search unavailable") from exc

    async def delete(self, source: str, ids: list[str]) -> None:
        collection = self.collections[source]
        if ids:
            escaped = json.dumps(ids, ensure_ascii=False)
            await asyncio.to_thread(self.client.delete, collection, filter=f"id in {escaped}")
            await asyncio.to_thread(self.client.flush, collection)

    async def health(self) -> bool:
        return bool(await asyncio.to_thread(self.client.has_collection, self.manual_collection))

    async def close(self) -> None:
        await asyncio.to_thread(self.client.close)
