import pytest

from apps.opspilot.models import LLMModel
from apps.opspilot.models.model_provider_mgmt import ModelVendor
from apps.opspilot.viewsets.llm_view import ObjFilter

pytestmark = pytest.mark.django_db


def _vendor(name, *, enabled):
    return ModelVendor.objects.create(name=name, vendor_type="openai", team=[1], enabled=enabled)


def _model(name, vendor, *, enabled):
    return LLMModel.objects.create(name=name, vendor=vendor, model=name, enabled=enabled, team=[1])


def _names(data):
    return set(ObjFilter(data=data, queryset=LLMModel.objects.all()).qs.values_list("name", flat=True))


def test_enabled_selection_requires_enabled_vendor_and_model():
    on = _vendor("on", enabled=True)
    off = _vendor("off", enabled=False)
    _model("keep", on, enabled=True)
    _model("model-off", on, enabled=False)
    _model("vendor-off", off, enabled=True)
    _model("orphan", None, enabled=True)

    assert _names({"enabled": "1"}) == {"keep"}


def test_unfiltered_list_keeps_disabled_models_and_vendors():
    on = _vendor("on", enabled=True)
    off = _vendor("off", enabled=False)
    _model("keep", on, enabled=True)
    _model("model-off", on, enabled=False)
    _model("vendor-off", off, enabled=True)

    assert _names({}) == {"keep", "model-off", "vendor-off"}


def test_disabled_query_returns_disabled_models_only():
    on = _vendor("on", enabled=True)
    off = _vendor("off", enabled=False)
    _model("keep", on, enabled=True)
    _model("model-off", on, enabled=False)
    _model("vendor-off", off, enabled=True)

    assert _names({"enabled": "0"}) == {"model-off"}
