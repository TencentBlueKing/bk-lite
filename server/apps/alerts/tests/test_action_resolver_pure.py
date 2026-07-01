import pytest
from apps.alerts.action.resolver import resolve_params
from apps.alerts.action.exceptions import ConfigError


PAYLOAD = {"labels.service": "nginx", "labels.disk": 95, "level": "1"}
SCRIPT_PARAMS = [{"name": "service", "default": ""}, {"name": "threshold", "default": "90"}]


def test_field_and_const_binding():
    bindings = [
        {"name": "service", "from": "field", "value": "labels.service"},
        {"name": "threshold", "from": "const", "value": "80"},
    ]
    out = resolve_params(PAYLOAD, bindings, SCRIPT_PARAMS)
    assert out == [{"name": "service", "value": "nginx"}, {"name": "threshold", "value": "80"}]


def test_missing_field_falls_back_to_default():
    bindings = [{"name": "service", "from": "field", "value": "labels.notexist"}]
    out = resolve_params(PAYLOAD, bindings, SCRIPT_PARAMS)
    assert out == [{"name": "service", "value": ""}]


def test_missing_field_no_default_raises_config_error():
    bindings = [{"name": "service", "from": "field", "value": "labels.notexist"}]
    script_params = [{"name": "service"}]
    with pytest.raises(ConfigError):
        resolve_params(PAYLOAD, bindings, script_params)
