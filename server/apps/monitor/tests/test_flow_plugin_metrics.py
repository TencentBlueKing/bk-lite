import json
from pathlib import Path


FLOW_METRICS_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf"


def test_flow_traffic_metric_queries_use_effective_sampling_rate():
    metric_files = sorted(FLOW_METRICS_ROOT.glob("*/**/metrics.json"))
    flow_metric_files = [
        path
        for path in metric_files
        if path.parts[-3] in {"netflow", "sflow"}
    ]

    assert flow_metric_files

    missing_sampling_rate_queries = []
    for path in flow_metric_files:
        payload = json.loads(path.read_text())
        for metric in payload.get("metrics", []):
            query = metric.get("query", "")
            if "flow_bytes_" in query and "effective_sampling_rate" not in query:
                missing_sampling_rate_queries.append(f"{path.relative_to(FLOW_METRICS_ROOT)}:{metric['name']}")

    assert missing_sampling_rate_queries == []
