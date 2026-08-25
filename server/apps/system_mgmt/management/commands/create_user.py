import uuid

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import Group, Role, User
from django.contrib.auth.hashers import check_password, make_password
from django.core.management import BaseCommand, CommandError
from django.db import IntegrityError, transaction


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
        parser.add_argument(
            "--update_existing_password",
            action="store_true",
            help="显式迁移仍使用 legacy 默认密码的既有用户；仅供受控初始化流程使用",
        )

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        email = options.get("email", "test@domain.com")
        display_name = options.get("display_name") or username
        is_superuser = options.get("is_superuser", False)
        update_existing_password = options.get("update_existing_password", False)

        # 受控密码迁移只允许命中默认域用户；锁内重读避免并发轮换覆盖。
        if update_existing_password:
            with transaction.atomic():
                migration_user = User.objects.select_for_update().filter(username=username, domain="domain.com").first()
                if migration_user:
                    if check_password(password, migration_user.password):
                        self.stdout.write(self.style.SUCCESS(f"用户密码已是目标值，无需迁移: {username}"))
                        return
                    if not check_password("password", migration_user.password):
                        self.stdout.write(self.style.SUCCESS(f"用户密码已完成轮换，不执行迁移: {username}"))
                        return
                    migration_user.password = make_password(password)
                    migration_user.save()
                    self.stdout.write(self.style.SUCCESS(f"成功迁移用户密码: {username}"))
                    return

        # 保留既有命令的全域同名 no-op 语义，并在锁内重新判定。
        try:
            with transaction.atomic():
                if User.objects.select_for_update().filter(username=username).exists():
                    self.stdout.write(self.style.ERROR(f"用户 {username} 已存在"))
                    return
                user = User.objects.create(
                    user_id=str(uuid.uuid4()),
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
            return
        except IntegrityError as error:
            # 多个 release 实例可能同时完成“用户不存在”的锁前检查。唯一约束会让
            # 后提交者在这里失败；若目标用户已经由竞争事务完整创建，则沿用既有
            # “同名用户 no-op”契约，其余完整性错误仍按初始化失败处理。
            if User.objects.filter(username=username, domain="domain.com").exists():
                self.stdout.write(self.style.ERROR(f"用户 {username} 已存在"))
                return
            caught_error = error
        except Exception as error:
            caught_error = error
        self.stdout.write(self.style.ERROR(f"创建用户时出错: {caught_error}"))
        raise CommandError(f"创建用户失败: {type(caught_error).__name__}") from caught_error
