import json
from pathlib import Path


VECTOR_COLLECTOR_DEFINITION = (
    Path(__file__).resolve().parents[1] / "support-files" / "collectors" / "Vector.json"
)


def test_vector_nats_tls_configs_use_verify_certificate_field():
    collectors = json.loads(VECTOR_COLLECTOR_DEFINITION.read_text())

    for collector in collectors:
        default_config = collector["default_config"]
        config_text = "\n".join(
            value for value in default_config.values() if isinstance(value, str)
        )

        assert "skip_cert_verify" not in config_text
        assert "verify_certificate = true" in config_text
