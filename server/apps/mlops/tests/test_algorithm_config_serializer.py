import pydantic.root_model  # noqa

import pytest
from rest_framework import serializers as drf_serializers

from apps.mlops.serializers.algorithm_config import AlgorithmConfigSerializer

pytestmark = pytest.mark.unit


def _validate(value):
    return AlgorithmConfigSerializer().validate_form_config(value)


def test_validate_form_config_empty_passthrough():
    assert _validate({}) == {}
    assert _validate(None) is None


def test_validate_form_config_non_dict_raises():
    with pytest.raises(drf_serializers.ValidationError) as exc:
        _validate(["not", "a", "dict"])
    assert "对象" in str(exc.value.detail)


def test_validate_form_config_hyperopt_not_list_raises():
    with pytest.raises(drf_serializers.ValidationError) as exc:
        _validate({"hyperopt_config": {"key": "x"}})
    assert "数组" in str(exc.value.detail)


def test_validate_form_config_hyperopt_item_not_dict_raises():
    with pytest.raises(drf_serializers.ValidationError) as exc:
        _validate({"hyperopt_config": ["bad"]})
    assert "对象" in str(exc.value.detail)


def test_validate_form_config_hyperopt_item_missing_key_raises():
    with pytest.raises(drf_serializers.ValidationError) as exc:
        _validate({"hyperopt_config": [{"label": "no key"}]})
    assert "key" in str(exc.value.detail)


def test_validate_form_config_valid_hyperopt_passes():
    value = {"hyperopt_config": [{"key": "n_estimators", "type": "int"}]}
    assert _validate(value) == value
