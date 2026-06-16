import json
import re
from pathlib import Path


TELEGRAF_COLLECTOR_DEFINITION = (
    Path(__file__).resolve().parents[1] / "support-files" / "collectors" / "Telegraf.json"
)


def test_telegraf_default_config_includes_passive_flow_udp_listeners():
    collectors = json.loads(TELEGRAF_COLLECTOR_DEFINITION.read_text())

    for collector in collectors:
        add_config = collector["default_config"]["add_config"]

        assert "[[inputs.netflow]]" in add_config
        assert 'service_address = "udp://:2055"' in add_config
        assert "[[inputs.sflow]]" in add_config
        assert 'service_address = "udp://:6343"' in add_config
        assert "[[processors.starlark]]" in add_config
        assert "FLOW_ASSET_MAP_JSON" in add_config
        assert "effective_sampling_rate" in add_config
        assert "fallback_sampling_rate" in add_config
        assert "SAMPLING_INTERVAL" in add_config
        assert "samplingRate" in add_config
        assert "$${FLOW_ASSET_MAP_JSON" not in add_config
        assert "${FLOW_ASSET_MAP_JSON:-{}}" not in add_config
        starlark_source = add_config.split("[processors.starlark.constants]")[0]
        assert '"${FLOW_ASSET_MAP_JSON}"' not in starlark_source
        assert 'flow_asset_map_json == "$" + "{FLOW_ASSET_MAP_JSON}"' in add_config
        assert 'return "{}"' in add_config
        assert "FLOW_ASSET_MAP = json.decode(_flow_asset_map_json())" in add_config
        assert "flow_asset_map_json = '${FLOW_ASSET_MAP_JSON}'" in add_config


def test_telegraf_flow_sampling_fields_only_use_reported_device_fields():
    collectors = json.loads(TELEGRAF_COLLECTOR_DEFINITION.read_text())

    for collector in collectors:
        add_config = collector["default_config"]["add_config"]
        match = re.search(r"FLOW_SAMPLING_FIELDS = \[(?P<fields>[^\]]+)\]", add_config)
        assert match is not None
        fields = re.findall(r'"([^"]+)"', match.group("fields"))
        assert fields == [
            "SAMPLING_INTERVAL",
            "SAMPLING_ALGORITHM",
            "sampling_rate",
            "samplingRate",
        ]
