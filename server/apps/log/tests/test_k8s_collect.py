from types import SimpleNamespace

import pytest

from apps.log.models import CollectInstance, CollectType
from apps.log.services.k8s_collect import K8sLogCollectService


@pytest.mark.django_db
def test_create_k8s_collect_instance_rolls_back_when_organization_insert_fails(mocker):
    collect_type = CollectType.objects.create(name="kubernetes", collector="filebeat", icon="")
    mocker.patch(
        "apps.log.services.k8s_collect.CollectInstanceOrganization.objects.bulk_create",
        side_effect=RuntimeError("organization insert failed"),
    )

    with pytest.raises(RuntimeError, match="organization insert failed"):
        K8sLogCollectService.create_k8s_collect_instance(
            {
                "id": "k8s-demo",
                "name": "k8s-demo",
                "collect_type_id": collect_type.id,
                "organizations": [2],
            }
        )

    assert not CollectInstance.objects.filter(id="k8s-demo").exists()


@pytest.mark.django_db
def test_check_collect_status_uses_iso8601_time_range(mocker):
    collect_instance = SimpleNamespace(id="k8s-demo")

    filter_mock = mocker.patch("apps.log.services.k8s_collect.CollectInstance.objects.filter")
    filter_mock.return_value.first.return_value = collect_instance

    search_logs = mocker.patch(
        "apps.log.services.k8s_collect.SearchService.search_logs",
        return_value=[{"_msg": "reported"}],
    )

    result = K8sLogCollectService.check_collect_status("k8s-demo")

    assert result is True
    search_logs.assert_called_once()
    _, start_time, end_time, limit = search_logs.call_args.args
    assert start_time.count("T") == 1
    assert end_time.count("T") == 1
    assert " " not in start_time
    assert " " not in end_time
    assert limit == 1
