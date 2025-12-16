import logging

from django.core.management import BaseCommand
from django.db import transaction

from apps.system_mgmt.models import Group, User

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "清洗默认组数据"

    def handle(self, *args, **options):
        try:
            logger.info("开始检查默认组数据...")

            group = Group.objects.filter(id=1).first()

            if not group:
                # ID=1 的组不存在，创建默认组
                logger.info("ID=1 的组不存在，创建默认组")
                with transaction.atomic():
                    Group.objects.create(name="Default", parent_id=0, id=1)
                    user_count = User.objects.all().update(group_list=[1])
                    logger.info(f"已创建默认组，并更新 {user_count} 个用户的组列表")

                self.stdout.write(self.style.SUCCESS("✓ 已创建默认组并更新用户"))
                return

            # ID=1 的组存在，检查是否符合要求
            if group.name == "Default" and group.parent_id == 0:
                logger.info("默认组数据正确，无需清洗")
                self.stdout.write(self.style.SUCCESS("✓ 默认组数据正确"))
                return

            # 需要清洗：将现有 ID=1 的组移到新 ID，然后创建正确的默认组
            logger.warning(f"ID=1 的组数据不正确 (name={group.name}, parent_id={group.parent_id})，开始清洗...")

            with transaction.atomic():
                # 计算新 ID
                max_group = Group.objects.all().order_by("-id").first()
                new_id = max_group.id + 1 if max_group else 2
                logger.info(f"将旧组 ID=1 迁移到 ID={new_id}")

                # 更新所有关联用户的 group_list
                affected_users = User.objects.filter(group_list__contains=[1])
                user_count = affected_users.count()
                logger.info(f"找到 {user_count} 个用户需要更新组列表")

                for user in affected_users:
                    if 1 in user.group_list:
                        user.group_list.remove(1)
                        user.group_list.append(new_id)
                        user.save(update_fields=["group_list"])

                # 删除旧的 ID=1 组（因为 ID 是主键，不能直接修改）
                group.delete()

                # 使用原来的属性创建新 ID 的组
                Group.objects.create(
                    id=new_id,
                    name=group.name,
                    description=group.description,
                    parent_id=group.parent_id,
                    external_id=group.external_id,
                    is_virtual=group.is_virtual,
                )

                # 创建正确的默认组
                Group.objects.create(name="Default", parent_id=0, id=1)

                logger.info(f"清洗完成：旧组已迁移到 ID={new_id}，已创建正确的默认组")

            self.stdout.write(self.style.SUCCESS(f"✓ 清洗完成：更新了 {user_count} 个用户，旧组迁移到 ID={new_id}"))

        except Exception as e:
            logger.error(f"清洗默认组数据失败: {str(e)}", exc_info=True)
            self.stdout.write(self.style.ERROR(f"✗ 清洗失败: {str(e)}"))
            raise
