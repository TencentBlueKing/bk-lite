from django.core.management.base import BaseCommand

from apps.core.models.maintainer_info import maintainer_kwargs
from apps.system_mgmt.models import NotificationTag

INITIAL_NOTIFICATION_TAGS = (("system", "itsm"),)


def init_notification_tags():
    for key, value in INITIAL_NOTIFICATION_TAGS:
        NotificationTag.objects.get_or_create(key=key, value=value, defaults=maintainer_kwargs())


class Command(BaseCommand):
    help = "初始化通知渠道标签候选。只写入候选行，不给已有渠道打标签。"

    def handle(self, *args, **options):
        init_notification_tags()
        self.stdout.write(self.style.SUCCESS("通知渠道标签候选初始化完成"))
