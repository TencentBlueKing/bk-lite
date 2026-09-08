import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _request():
    return SimpleNamespace(
        user=SimpleNamespace(
            username="alice",
            group_list=[{"id": 1}],
            group_tree=[],
            roles=[],
            permission={"auto_collection-View"},
            is_superuser=False,
            locale="zh-Hans",
        ),
        COOKIES={"current_team": "1", "include_children": "0"},
        api_pass=False,
    )


def test_task_status_splits_ipmi_and_redfish_while_preserving_protocol_total():
    from apps.cmdb.constants.constants import CollectRunStatusType
    from apps.cmdb.views.collect import CollectModelViewSet

    request = _request()
    view = CollectModelViewSet()
    view.request = request
    view.action = "task_status"

    queryset = MagicMock(name="queryset")
    visible_queryset = MagicMock(name="visible_queryset")
    values_queryset = MagicMock(name="values_queryset")
    queryset.filter.return_value = visible_queryset
    visible_queryset.values.return_value = values_queryset
    status_rows = [
        {
            "model_id": "physcial_server",
            "driver_type": "protocol",
            "exec_status": CollectRunStatusType.RUNNING,
            "params__collection_protocol": None,
            "total": 1,
        },
        {
            "model_id": "physcial_server",
            "driver_type": "protocol",
            "exec_status": CollectRunStatusType.ERROR,
            "params__collection_protocol": "redfish",
            "total": 1,
        },
    ]
    values_queryset.annotate.return_value = status_rows

    with patch.object(CollectModelViewSet, "get_queryset", return_value=queryset):
        with patch.object(
            CollectModelViewSet,
            "get_queryset_by_permission",
            return_value=queryset,
        ):
            response = view.task_status(request)

    payload = json.loads(response.content)["data"]
    visible_queryset.values.assert_called_once_with(
        "model_id",
        "driver_type",
        "exec_status",
        "params__collection_protocol",
    )
    assert payload["physcial_server__protocol"]["running"] == 1
    assert payload["physcial_server__protocol"]["failed"] == 1
    assert payload["physcial_server__protocol__ipmi"]["running"] == 1
    assert payload["physcial_server__protocol__ipmi"]["failed"] == 0
    assert payload["physcial_server__protocol__redfish"]["failed"] == 1
    assert payload["physcial_server__protocol__redfish"]["running"] == 0
