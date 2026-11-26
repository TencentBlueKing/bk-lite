from django.core.management.base import BaseCommand

from apps.core.models.maintainer_info import DEFAULT_MAINTAINER_DOMAIN, SYSTEM_MAINTAINER
from apps.itsm.models import DataDictionary, DataDictionaryItem, NotifyTemplate, StatusTransition, TicketStatus
from apps.system_mgmt.models import CustomMenuGroup

STATUSES = (
    ("draft", "草稿", "#8c8c8c", False, 1),
    ("new", "新", "#1677ff", False, 2),
    ("processing", "处理中", "#fa8c16", False, 3),
    ("suspended", "挂起", "#722ed1", False, 4),
    ("finished", "已完成", "#52c41a", True, 5),
    ("terminated", "终止", "#f5222d", True, 6),
    ("cancelled", "撤销", "#595959", True, 7),
)

TRANSITIONS = (
    ("draft", "new", "提交"),
    ("new", "processing", "响应"),
    ("processing", "suspended", "挂起"),
    ("suspended", "processing", "恢复"),
    ("suspended", "cancelled", "撤销"),
    ("suspended", "finished", "关闭"),
    ("suspended", "terminated", "终止"),
    ("processing", "finished", "完成"),
    ("new", "cancelled", "撤销"),
    ("new", "suspended", "挂起"),
    ("new", "finished", "关闭"),
    ("new", "terminated", "终止"),
    ("processing", "new", "退回"),
    ("processing", "terminated", "终止"),
    ("processing", "cancelled", "撤销"),
    ("finished", "processing", "重新打开"),
    ("terminated", "processing", "重新打开"),
    ("cancelled", "processing", "重新打开"),
)

DICTIONARIES = {
    "priority": ("优先级", ("P1", "P2", "P3", "P4")),
    "urgency": ("紧急度", ("高", "中", "低")),
    "impact": ("影响度", ("高", "中", "低")),
}

TEMPLATES = (
    ("task.created", "任务待办", "你有新的待办：{{ title }}"),
    ("ticket.urge", "催办", "{{ title }} 被催办"),
    ("ticket.returned", "退回", "{{ title }} 已退回"),
    ("ticket.finished", "完成", "{{ title }} 已完成"),
)


def ensure_builtin_dictionary(key, actor):
    name, items = DICTIONARIES[key]
    dictionary, _ = DataDictionary.objects.get_or_create(domain=actor["domain"], key=key, defaults={"name": name, **actor})
    for order, label in enumerate(items, start=1):
        DataDictionaryItem.objects.get_or_create(
            dictionary=dictionary, key=label, defaults={"label": label, "order": order, "is_enabled": True, **actor}
        )


class Command(BaseCommand):
    help = "写入 ITSM 内置状态、流转、字典和通知模板"

    def handle(self, *args, **options):
        actor = {
            "created_by": SYSTEM_MAINTAINER,
            "updated_by": SYSTEM_MAINTAINER,
            "domain": DEFAULT_MAINTAINER_DOMAIN,
            "updated_by_domain": DEFAULT_MAINTAINER_DOMAIN,
        }
        # 单独初始化 ITSM 时也补齐菜单组；不覆盖管理员已有的启用或停用配置。
        if not CustomMenuGroup.objects.filter(app="itsm").exists():
            CustomMenuGroup.objects.get_or_create(
                app="itsm",
                display_name="默认菜单",
                defaults={"is_enabled": True, "is_build_in": True, "menus": [], **actor},
            )
        statuses = {}
        for key, name, color, terminal, order in STATUSES:
            status, _ = TicketStatus.objects.get_or_create(
                domain=DEFAULT_MAINTAINER_DOMAIN,
                key=key,
                defaults={"name": name, "color": color, "kind": TicketStatus.Kind.BUILTIN, "is_terminal": terminal, "order": order, **actor},
            )
            statuses[key] = status
        for source, target, name in TRANSITIONS:
            StatusTransition.objects.get_or_create(
                from_status=statuses[source],
                to_status=statuses[target],
                name=name,
                defaults={"is_builtin": True, **actor},
            )
        for key in DICTIONARIES:
            ensure_builtin_dictionary(key, actor)
        for event, title, content in TEMPLATES:
            NotifyTemplate.objects.get_or_create(
                domain=DEFAULT_MAINTAINER_DOMAIN,
                event=event,
                channel_type="site",
                defaults={"title_tpl": title, "content_tpl": content, "is_builtin": True, **actor},
            )
        self.stdout.write(self.style.SUCCESS("init_itsm done"))
