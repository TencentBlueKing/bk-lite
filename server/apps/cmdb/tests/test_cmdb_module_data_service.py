import pytest

from apps.cmdb.constants.constants import CollectPluginTypes, PERMISSION_TASK
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.nats.nats import get_cmdb_module_data


@pytest.mark.django_db
def test_permission_task_enum_returns_total_count_across_pages():
    for index in range(3):
        CollectModels.objects.create(
            name=f"普通采集-{index}",
            task_type=CollectPluginTypes.HOST,
            model_id="host",
            driver_type="ordinary",
            cycle_value_type="cycle",
            team=[1],
        )

    result = get_cmdb_module_data(PERMISSION_TASK, CollectPluginTypes.HOST, 1, 2, 1)

    assert result["count"] == 3
    assert len(result["items"]) == 2
