from apps.monitor.models import MonitorInstance
from apps.monitor.services.monitor_instance import InstanceSearch
from apps.monitor.services.monitor_object import MonitorObjectService


def test_monitor_object_service_projects_identity_fields_only(db):
    queryset = MonitorObjectService._project_instance_identity(MonitorInstance.objects.all())
    sql = str(queryset.query)

    assert '"monitor_monitorinstance"."id"' in sql
    assert '"monitor_monitorinstance"."name"' in sql
    assert '"monitor_monitorinstance"."cloud_region_id"' not in sql
    assert '"monitor_monitorinstance"."ip"' not in sql
    assert '"monitor_monitorinstance"."fallback_sampling_rate"' not in sql
    assert '"monitor_monitorinstance"."enabled_protocols"' not in sql


def test_instance_search_projects_identity_fields_only(db):
    queryset = InstanceSearch._project_instance_identity(MonitorInstance.objects.all())
    sql = str(queryset.query)

    assert '"monitor_monitorinstance"."id"' in sql
    assert '"monitor_monitorinstance"."name"' in sql
    assert '"monitor_monitorinstance"."cloud_region_id"' not in sql
    assert '"monitor_monitorinstance"."ip"' not in sql
    assert '"monitor_monitorinstance"."fallback_sampling_rate"' not in sql
    assert '"monitor_monitorinstance"."enabled_protocols"' not in sql
