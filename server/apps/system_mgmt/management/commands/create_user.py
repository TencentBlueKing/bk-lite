import logging

from django.contrib.auth.hashers import make_password
from django.core.management import BaseCommand

from apps.system_mgmt.models import Group, Role, User

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "创建用户"

    def add_arguments(self, parser):
        # 添加必填参数
        parser.add_argument("username", type=str, help="用户名")
        parser.add_argument("password", type=str, help="密码")
        # 添加可选参数
        parser.add_argument("--email", type=str, help="邮箱地址")
        parser.add_argument("--display_name", type=str, help="显示名称")
        parser.add_argument("--is_superuser", action="store_true", help="是否为超级用户")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        email = options.get("email", "test@domain.com")
        display_name = options.get("display_name") or username
        is_superuser = options.get("is_superuser", False)

        # 检查用户是否已存在
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.ERROR(f"用户 {username} 已存在"))
            return

        # 创建用户
        try:
            user = User.objects.create(
                username=username,
                password=make_password(password),  # 加密密码
                email=email,
                display_name=display_name,
                # 根据您的User模型设置其他字段
            )

            default_group, _ = Group.objects.get_or_create(name="Default", parent_id=0)
            user.group_list.append(default_group.id)
            if is_superuser:
                role, _ = Role.objects.get_or_create(name="admin", app="")
                user.role_list.append(role.id)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"成功创建用户: {username}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"创建用户时出错: {e}"))
