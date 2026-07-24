from django.db import transaction

from apps.core.logger import log_logger as logger
from apps.log.models import LogGroup, LogGroupOrganization
from apps.rpc.system_mgmt import SystemMgmt


def _get_default_organization_id():
    res = SystemMgmt(is_local_client=True).get_group_id("Default")
    organization = res.get("data") if isinstance(res, dict) and res.get("result") is True else None

    if isinstance(organization, bool) or not isinstance(organization, int) or organization <= 0:
        raise ValueError("无法获取有效的默认组织 ID")

    return organization


def init_stream():
    try:
        valid_relations = LogGroupOrganization.objects.filter(log_group_id="default", organization__gt=0)
        if valid_relations.exists():
            LogGroupOrganization.objects.filter(log_group_id="default", organization__lte=0).delete()
            return True

        organization = _get_default_organization_id()

        with transaction.atomic():
            log_group, _ = LogGroup.objects.get_or_create(
                id="default",
                defaults={"name": "Default", "created_by": "system", "updated_by": "system"},
            )
            if not LogGroupOrganization.objects.filter(log_group=log_group, organization__gt=0).exists():
                LogGroupOrganization.objects.get_or_create(
                    log_group=log_group,
                    organization=organization,
                    defaults={"created_by": "system", "updated_by": "system"},
                )
            LogGroupOrganization.objects.filter(log_group=log_group, organization__lte=0).delete()
        return True
    except Exception as exc:
        logger.exception(f"初始化默认日志分组失败，将在下次初始化重试: {type(exc).__name__}: {exc}")
        return False
