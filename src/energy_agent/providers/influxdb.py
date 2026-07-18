import asyncio
from collections import defaultdict
from datetime import datetime
from statistics import fmean
from typing import Any, cast


def summarize_points(points: list[tuple[datetime, float]]) -> dict[str, object]:
    ordered = sorted(points, key=lambda item: item[0])
    values = [point[1] for point in ordered]
    if not values:
        return {"point_count": 0, "missing": True, "quality": "no_data"}
    delta = values[-1] - values[0]
    trend = "rising" if delta > 0.01 else "falling" if delta < -0.01 else "stable"
    return {
        "first": values[0],
        "last": values[-1],
        "min": min(values),
        "max": max(values),
        "average": fmean(values),
        "trend": trend,
        "point_count": len(values),
        "missing": False,
        "quality": "good",
    }


class InfluxTimeseriesProvider:
    provider_type = "real"

    def __init__(self, client: Any, org: str, bucket: str, timeout_seconds: float) -> None:
        self.client = client
        self.org = org
        self.bucket = bucket
        self.timeout_seconds = timeout_seconds

    async def query(
        self,
        device_id: str,
        metrics: list[str],
        start_time: str,
        end_time: str,
        max_points: int,
    ) -> dict[str, object]:
        escaped_device = device_id.replace('"', '\\"')
        metric_filter = " or ".join(
            f'r.metric_name == "{metric.replace(chr(34), "")}"' for metric in metrics
        )
        flux = (
            f'from(bucket: "{self.bucket}")'
            f" |> range(start: {start_time}, stop: {end_time})"
            ' |> filter(fn: (r) => r._measurement == "pcs_metrics")'
            f' |> filter(fn: (r) => r.device_id == "{escaped_device}")'
            f" |> filter(fn: (r) => {metric_filter})"
            ' |> filter(fn: (r) => r._field == "value")'
            f" |> limit(n: {max_points})"
        )

        def execute() -> list[Any]:
            return cast(list[Any], self.client.query_api().query(flux, org=self.org))

        tables = await asyncio.wait_for(asyncio.to_thread(execute), self.timeout_seconds)
        grouped: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        for table in tables:
            for record in table.records:
                grouped[str(record.values.get("metric_name"))].append(
                    (record.get_time(), float(record.get_value()))
                )
        return {metric: summarize_points(grouped.get(metric, [])) for metric in metrics}
