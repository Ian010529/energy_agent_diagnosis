import uuid

import pytest

from energy_agent.core.errors import MilvusSchemaMismatchError
from energy_agent.providers.milvus import MilvusVectorProvider

pytestmark = pytest.mark.integration


def vector(index: int) -> list[float]:
    output = [0.0] * 1024
    output[index] = 1.0
    return output


@pytest.mark.asyncio
async def test_real_milvus_collections_upsert_rank_delete_and_dimension_validation() -> None:
    suffix = uuid.uuid4().hex[:8]
    provider = MilvusVectorProvider(
        uri="http://localhost:19530",
        token=None,
        manual_collection=f"manual_test_{suffix}",
        ticket_collection=f"ticket_test_{suffix}",
        dimension=1024,
        metric_type="COSINE",
    )
    try:
        await provider.ensure_collections()
        rows = [
            {
                "id": "CHUNK-A",
                "source_id": "DOC-A",
                "device_type": "PCS",
                "device_model": "SC5000",
                "manufacturer": "EnergyCo",
                "alarm_name": "温度告警",
                "index_generation": "g1",
                "verified": True,
                "effective": True,
                "embedding": vector(0),
            },
            {
                "id": "CHUNK-B",
                "source_id": "DOC-B",
                "device_type": "PCS",
                "device_model": "SC5000",
                "manufacturer": "EnergyCo",
                "alarm_name": "通信告警",
                "index_generation": "g1",
                "verified": True,
                "effective": True,
                "embedding": vector(1),
            },
        ]
        await provider.upsert("manual", rows)
        hits = await provider.search("manual", vector(0), ["CHUNK-A", "CHUNK-B"], limit=2)
        assert [item["id"] for item in hits] == ["CHUNK-A", "CHUNK-B"]
        await provider.upsert("manual", rows)
        await provider.delete("manual", ["CHUNK-A"])
        remaining = await provider.search("manual", vector(0), ["CHUNK-A"], limit=2)
        assert remaining == []
        with pytest.raises(MilvusSchemaMismatchError):
            await provider.search("manual", [1.0], ["CHUNK-B"], limit=1)
    finally:
        await provider.close()
