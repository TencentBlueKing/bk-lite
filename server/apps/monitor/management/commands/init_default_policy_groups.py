from django.core.management.base import BaseCommand

from apps.core.logger import monitor_logger as logger
from apps.core.logger import safe_exception_info
from apps.monitor.models import MonitorObject, PolicyGroupDefault, PolicyTemplate
from apps.monitor.services.policy_group import PolicyGroupService
from apps.system_mgmt.utils.group_utils import GroupUtils


class Command(BaseCommand):
    help = "为 Default 组织按监控对象生成默认策略组"

    def handle(self, *args, **options):
        default_group = GroupUtils.active_queryset(name="Default", parent_id=0).order_by("id").first()
        if default_group is None:
            logger.warning("event=policy_group_default_init_skipped reason=default_organization_missing failed_stage=resolve_organization")
            self.stdout.write("默认策略组初始化跳过：Default 组织不存在")
            return

        organization_id = default_group.id
        object_ids = list(
            PolicyTemplate.objects.filter(template_type=PolicyTemplate.TYPE_BUILTIN)
            .order_by("monitor_object_id")
            .values_list("monitor_object_id", flat=True)
            .distinct()
        )
        created = 0
        skipped = 0
        failed = 0
        for monitor_object in MonitorObject.objects.filter(id__in=object_ids).order_by("id"):
            had_pointer = PolicyGroupDefault.objects.filter(organization=organization_id, monitor_object=monitor_object).exists()
            try:
                PolicyGroupService.ensure_default(organization=organization_id, monitor_object=monitor_object, operator="system")
            except Exception as error:  # noqa: BLE001 - 单个对象失败继续处理其余对象
                failed += 1
                logger.error(
                    "event=policy_group_default_init_failed organization=%s monitor_object_id=%s failed_stage=ensure_default error_type=%s",
                    organization_id,
                    monitor_object.id,
                    type(error).__name__,
                    exc_info=safe_exception_info(error),
                )
                continue
            if had_pointer:
                outcome = "skipped"
                skipped += 1
            elif PolicyGroupDefault.objects.filter(organization=organization_id, monitor_object=monitor_object).exists():
                outcome = "created"
                created += 1
            else:
                outcome = "unchanged"
            logger.debug(
                "event=policy_group_default_init_object organization=%s monitor_object_id=%s outcome=%s",
                organization_id,
                monitor_object.id,
                outcome,
            )

        logger.info(
            "event=policy_group_default_init_finished organization=%s created=%s skipped=%s failed=%s",
            organization_id,
            created,
            skipped,
            failed,
        )
        self.stdout.write(f"默认策略组初始化完成 organization={organization_id} created={created} skipped={skipped} failed={failed}")
