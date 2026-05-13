from types import SimpleNamespace

import pytest

from apps.log.services.k8s_collect import K8sLogCollectService


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
