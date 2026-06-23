"""IPAM 对账登记表模型 + 对账逻辑（本任务先放模型用例，后续任务追加）。"""
import pytest

pytestmark = pytest.mark.django_db


def test_reconcile_source_model_fields():
    from apps.cmdb.models.ipam_models import IPAMReconcileSource
    src = IPAMReconcileSource.objects.create(model_id="host", ip_attr_id="ip_addr", enabled=True)
    assert src.model_id == "host"
    assert src.enabled is True
    assert IPAMReconcileSource.objects.filter(enabled=True).count() == 1
