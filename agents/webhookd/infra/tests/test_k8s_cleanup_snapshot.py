"""执行 manifest 中的真实采集脚本，网络在 curl 边界替换。"""
import os
import subprocess
from pathlib import Path

import pytest
import yaml

MANIFEST = Path(__file__).resolve().parents[2] / "bk-lite-resource-collector.yaml"


def config():
    return next(
        doc["data"] for doc in yaml.safe_load_all(MANIFEST.read_text()) if doc and doc.get("metadata", {}).get("name") == "telegraf-resource-config"
    )


@pytest.mark.parametrize("failed", [False, True])
def test_scrape_emits_counts_and_single_timestamp_only_after_success(tmp_path, failed):
    script = tmp_path / "collect.sh"
    script.write_text(config()["collect-resource.sh"])
    curl = tmp_path / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        + (
            "exit 22\n"
            if failed
            else """for arg; do target="$arg"; done
cat > "$target" <<'EOF'
# HELP kube_namespace_labels Kubernetes namespace labels
# TYPE kube_namespace_labels gauge
kube_namespace_labels{namespace="default"} 1
# HELP kube_node_info Information about a cluster node
# TYPE kube_node_info gauge
kube_node_info{node="n1"} 1
EOF
"""
        )
    )
    curl.chmod(0o755)
    result = subprocess.run(
        ["/bin/sh", str(script)], env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"]}, text=True, capture_output=True
    )
    if failed:
        assert result.returncode != 0
        assert "cmdb_k8s_snapshot" not in result.stdout
    else:
        assert result.returncode == 0, result.stderr
        rows = [line for line in result.stdout.splitlines() if line and not line.startswith("#")]
        assert len(rows) == 26  # 2 个资源 + 23 种指标计数 + 1 个时间标记
        assert len({row.split()[-1] for row in rows}) == 1
        assert 'cmdb_k8s_snapshot_count{resource_metric="kube_pod_info"} 0 ' in result.stdout
        assert 'cmdb_k8s_snapshot_count{resource_metric="kube_namespace_labels"} 1 ' in result.stdout
        assert 'snapshot_contract_version="1"' in result.stdout


def test_telegraf_preserves_source_timestamps_and_metric_names():
    import tomllib

    data = config()
    parsed = tomllib.loads(data["telegraf.conf"])
    source = parsed["inputs"]["exec"][0]
    assert source["data_format"] == "prometheus"
    assert source["prometheus_metric_version"] == 2
    assert source["prometheus_ignore_timestamp"] is False
    assert source["name_override"] == "prometheus"
