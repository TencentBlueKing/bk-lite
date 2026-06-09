import sys
from pathlib import Path

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

from tasks.collectors.host_wmi.errors import WmiError, classify_wmi_error
from tasks.collectors.host_wmi.metrics import wmi_results_to_prometheus
from tasks.collectors.host_wmi.modules import resolve_modules


def test_resolve_modules_accepts_comma_separated_values():
    assert resolve_modules("cpu, mem,invalid,disk") == ["cpu", "mem", "disk"]


def test_resolve_modules_accepts_arrays_and_defaults_when_empty():
    assert resolve_modules(["net", "processes", "bad"]) == ["net", "processes"]
    assert resolve_modules("bad,unknown") == ["cpu", "mem", "disk", "net"]


def test_classify_wmi_error_normalizes_common_failures():
    assert classify_wmi_error(PermissionError("access denied")) == "dcom_access_denied"
    assert classify_wmi_error(TimeoutError("timed out")) == "query_timeout"
    assert classify_wmi_error(WmiError("bad namespace", "namespace_not_found")) == "namespace_not_found"


def test_wmi_results_to_prometheus_emits_host_metrics():
    output = wmi_results_to_prometheus(
        {
            "cpu": {"usage_percent": 12.5, "core_count": 4},
            "mem": {
                "total_bytes": 8589934592,
                "available_bytes": 4294967296,
                "used_bytes": 4294967296,
                "used_percent": 50.0,
            },
            "disk": [
                {
                    "device": "C:",
                    "total_bytes": 1000,
                    "free_bytes": 250,
                    "used_bytes": 750,
                    "used_percent": 75.0,
                }
            ],
        },
        {
            "instance_id": "region_os_10.0.0.8",
            "instance_type": "os",
            "collect_type": "http",
            "config_type": "windows_wmi",
        },
        host="10.0.0.8",
        timestamp=1700000000000,
    )

    base = 'instance_id="region_os_10.0.0.8",instance_type="os",collect_type="http",config_type="windows_wmi",host="10.0.0.8"'
    assert f"host_cpu_usage_percent_gauge{{{base}}} 12.5 1700000000000" in output
    assert f"host_cpu_core_count_gauge{{{base}}} 4 1700000000000" in output
    assert f"host_mem_used_percent_gauge{{{base}}} 50 1700000000000" in output
    assert f'host_disk_used_percent_gauge{{{base},device="C:"}} 75 1700000000000' in output
