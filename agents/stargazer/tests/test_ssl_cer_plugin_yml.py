from pathlib import Path

import yaml


def test_ssl_cer_plugin_uses_tls_preflight_and_protocol_collector():
    path = Path("plugins/inputs/ssl_cer/plugin.yml")
    plugin = yaml.safe_load(path.read_text())
    assert plugin["name"] == "ssl_cer"
    assert plugin["metadata"]["model_id"] == "ssl_cer"
    assert plugin["default_executor"] == "protocol"
    executor = plugin["executors"]["protocol"]
    assert executor["collector"]["module"] == "plugins.inputs.ssl_cer.ssl_cer_info"
    assert executor["collector"]["class"] == "SslCerInfo"
    assert executor["target_policy"] == {"mode": "tls", "port": 443}
