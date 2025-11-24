from apps.log.models import LogGroup, LogGroupOrganization
from apps.rpc.system_mgmt import SystemMgmt


def init_stream():

    if not LogGroup.objects.filter(id='default').exists():
        LogGroup.objects.create(id='default', name='Default', created_by="system", updated_by="system")

        client = SystemMgmt(is_local_client=True)
        res = client.get_group_id("Default")

        LogGroupOrganization.objects.create(
            log_group_id='default', organization=res.get("data", 0), created_by="system", updated_by="system")
