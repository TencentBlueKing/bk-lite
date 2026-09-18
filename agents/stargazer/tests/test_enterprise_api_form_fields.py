"""Verify the shipped enterprise collectors consume the connection fields shown by CMDB."""
import importlib.util
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[3] / "enterprise/agents/stargazer/enterprise/plugins/inputs"


@pytest.mark.parametrize("model,class_name", [("nacos", "NacosInfo"), ("server_bmc", "ServerBmcInfo")])
@pytest.mark.parametrize("raw,expected", [(True, True), (False, False), ("true", True), ("false", False)])
def test_api_collector_uses_form_certificate_verification(model, class_name, raw, expected):
    path = SOURCE_ROOT / model / (model + "_info.py")
    spec = importlib.util.spec_from_file_location("form_contract_" + model, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    collector = getattr(module, class_name)(
        {"host": "example.test", "port": 8443, "scheme": "https", "username": "test-user", "password": "test-password", "verify_tls": raw}
    )
    assert collector.session.verify is expected
    assert collector.port == 8443
    assert collector.scheme == "https"
    assert collector.username == "test-user"
    assert collector.password == "test-password"
    collector.session.close()
