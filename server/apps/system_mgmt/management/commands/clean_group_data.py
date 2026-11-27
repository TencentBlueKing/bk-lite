from django.core.management import BaseCommand
from django.db import transaction

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import Group
from apps.system_mgmt.utils.group_utils import GroupUtils


class Command(BaseCommand):
    help = "清洗默认组数据"

    def handle(self, *args, **options):
        try:
            logger.info("开始检查默认组数据...")

            if GroupUtils.builtin_root() is not None:
                logger.info("默认组数据正确，无需清洗")
                self.stdout.write(self.style.SUCCESS("✓ 默认组数据正确"))
                return

            with transaction.atomic():
                Group.objects.create(name="Default", parent_id=0, is_builtin=True)
                logger.info("已创建内置根组织")

            self.stdout.write(self.style.SUCCESS("✓ 已创建默认组"))

        except Exception as e:
            logger.error(f"清洗默认组数据失败: {str(e)}", exc_info=True)
            self.stdout.write(self.style.ERROR(f"✗ 清洗失败: {str(e)}"))
            raise
