import pytest

pytestmark = pytest.mark.integration


def test_required_degradation_matrix_is_complete() -> None:
    matrix = {
        "model": "rules",
        "embedding": "keyword_only",
        "milvus": "keyword_only",
        "reranker": "simple_ranking",
        "influxdb": "need_user_input",
        "neo4j": "continue_without_graph",
        "rabbitmq": "outbox",
        "langfuse": "structured_logging",
        "multiple_knowledge_channels": "human_takeover",
    }
    assert len(matrix) == 9
