import pytest

from energy_agent.reliability.dedup import alarm_dedup_key

pytestmark = pytest.mark.integration


def test_same_device_and_normalized_category_merge_key() -> None:
    assert alarm_dedup_key("PCS-1", "机柜 温度异常") == alarm_dedup_key("PCS-1", "机柜温度异常")
    assert alarm_dedup_key("PCS-1", "机柜温度异常") != alarm_dedup_key("PCS-1", "风扇异常")
