"""
统一初始化命令 - 在单个 Python 进程中执行所有初始化任务
避免多次启动 Python 进程，大幅提升启动速度
"""

import os
from pathlib import Path

from django.apps import apps as django_apps
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.logger import logger
from apps.core.utils.loader import preload_language_cache

_ADMIN_PASSWORD_FILE_MAX_CHARS = 4096


class Command(BaseCommand):
    help = "批量执行初始化命令，根据 INSTALL_APPS 环境变量选择性初始化"

    def add_arguments(self, parser):
        parser.add_argument("--apps", type=str, default="", help="逗号分隔的应用列表，为空则初始化所有应用")
        parser.add_argument(
            "--continue-on-error",
            action="store_true",
            help="初始化失败时继续执行后续模块，并在末尾输出失败列表",
        )

    def handle(self, *args, **options):
        self._verify_critical_schema()

        apps = options["apps"].strip()
        continue_on_error = options["continue_on_error"]

        # 如果为空，初始化所有应用
        if not apps:
            apps_list = [
                "system_mgmt",
                "cmdb",
                "monitor",
                "node_mgmt",
                "alerts",
                "operation_analysis",
                "opspilot",
                "log",
                "mlops",
                "patch_mgmt",
            ]
        else:
            apps_list = [app.strip() for app in apps.split(",")]

        self.stdout.write(self.style.SUCCESS(f"开始批量初始化，目标模块: {', '.join(apps_list)}"))

        # 预热语言缓存
        self._preload_language_cache()

        # 按模块执行初始化
        failed_apps = []
        for app in apps_list:
            try:
                if app == "system_mgmt":
                    self._init_system_mgmt()
                elif app == "cmdb":
                    self._init_cmdb()
                elif app == "console_mgmt":
                    self._init_console_mgmt()
                elif app == "monitor":
                    self._init_monitor()
                elif app == "node_mgmt":
                    self._init_node_mgmt()
                elif app == "alerts":
                    self._init_alerts()
                elif app == "operation_analysis":
                    self._init_operation_analysis()
                elif app == "opspilot":
                    self._init_opspilot()
                elif app == "log":
                    self._init_log()
                elif app == "mlops":
                    self._init_mlops()
                elif app == "patch_mgmt":
                    self._init_patch_mgmt()
                else:
                    self.stdout.write(self.style.WARNING(f"未知模块: {app}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"初始化 {app} 失败: {str(e)}"))
                if not continue_on_error:
                    raise
                failed_apps.append((app, str(e)))
                continue

        if failed_apps:
            failed_summary = "; ".join(f"{app}: {error}" for app, error in failed_apps)
            self.stdout.write(self.style.WARNING(f"批量初始化完成，失败模块: {failed_summary}"))
            return

        self.stdout.write(self.style.SUCCESS("批量初始化完成"))

    @staticmethod
    def _verify_critical_schema():
        """确保被权限读写链路硬依赖的表已完成迁移。"""
        try:
            permission_version_model = django_apps.get_model("system_mgmt", "UserPermissionVersion")
        except LookupError as error:
            raise RuntimeError("关键应用 system_mgmt 未安装，无法启动权限服务") from error
        permission_version_model.objects.values_list("id", flat=True).first()

    def _init_system_mgmt(self):
        """系统管理资源初始化"""
        self.stdout.write("系统管理资源初始化...")
        call_command("cleanup_opspilot_legacy_knowledge_menus")
        call_command("init_realm_resource")
        call_command("init_login_settings")
        self._bootstrap_admin()
        call_command("init_custom_menu")
        call_command("init_bk_login_settings")
        call_command("clean_group_data")

    def _bootstrap_admin(self) -> None:
        migrate_existing_password = self._should_migrate_admin_password()
        with transaction.atomic():
            if self._any_admin_username_exists() and not migrate_existing_password:
                return
            admin_password = self._get_admin_password()
            call_command(
                "create_user",
                "admin",
                admin_password,
                email="admin@bklite.net",
                is_superuser=True,
                update_existing_password=migrate_existing_password,
            )

    @staticmethod
    def _any_admin_username_exists() -> bool:
        user_model = django_apps.get_model("system_mgmt", "User")
        # create_user 历史上对任意域的同名用户均 no-op；这里保持同一存量判定，
        # 避免仅有外域 admin 的合法升级环境被新 Secret 门禁意外阻断。
        return user_model.objects.select_for_update().filter(username="admin").exists()

    @staticmethod
    def _has_managed_admin_password() -> bool:
        return bool(os.getenv("BK_INIT_ADMIN_PASSWORD", "").strip() or os.getenv("BK_INIT_ADMIN_PASSWORD_FILE", "").strip())

    @staticmethod
    def _get_admin_password() -> str:
        admin_password = os.getenv("BK_INIT_ADMIN_PASSWORD", "").strip()
        if admin_password:
            return admin_password

        password_file = os.getenv("BK_INIT_ADMIN_PASSWORD_FILE", "").strip()
        if not password_file:
            logger.warning("未配置管理员引导凭据，按产品默认使用内置初始密码；请登录后尽快修改")
            return "password"
        try:
            with Path(password_file).open(encoding="utf-8") as file:
                password = file.read(_ADMIN_PASSWORD_FILE_MAX_CHARS + 1)
        except (OSError, UnicodeError) as error:
            raise CommandError(f"无法读取管理员密码 Secret 文件: {type(error).__name__}") from error
        if len(password) > _ADMIN_PASSWORD_FILE_MAX_CHARS:
            raise CommandError("管理员密码 Secret 文件内容过大")
        password = password.strip()
        if not password:
            raise CommandError("管理员密码 Secret 文件不能为空")
        return password

    @staticmethod
    def _should_migrate_admin_password() -> bool:
        value = os.getenv("BK_INIT_ADMIN_PASSWORD_MIGRATE_EXISTING", "").strip().lower()
        if value in {"", "false", "0", "no"}:
            return False
        if value in {"true", "1", "yes"}:
            if not Command._has_managed_admin_password():
                raise CommandError("迁移既有管理员密码必须配置 BK_INIT_ADMIN_PASSWORD 或 BK_INIT_ADMIN_PASSWORD_FILE")
            return True
        raise CommandError("BK_INIT_ADMIN_PASSWORD_MIGRATE_EXISTING 仅支持 true/false")

    def _init_cmdb(self):
        """CMDB资源初始化"""
        self.stdout.write("CMDB资源初始化...")
        call_command("model_init")
        call_command("init_oid")
        call_command("init_port_fingerprint")
        call_command("update_collect_task_data")
        call_command("init_field_groups")
        call_command("init_display_fields")
        call_command("cmdb_migrate_scalar_to_list")
        call_command("migrate_field_constraints")
        call_command("reconcile_node_mgmt_sync")
        # UUID 存量清洗：只注册运行期任务并投递一次；禁止在此同步 --apply（避免挡 supervisord）。
        try:
            from apps.cmdb.tasks.uuid_migration import ensure_uuid_migration_periodic_task, migrate_cmdb_instance_uuid_runtime

            ensure_uuid_migration_periodic_task()
            try:
                migrate_cmdb_instance_uuid_runtime.delay()
            except Exception as exc:
                # Broker 暂不可达时不阻断启动；周期任务会在 Beat/Worker 就绪后收敛。
                logger.warning("投递 CMDB UUID 运行期清洗任务失败（将由周期任务重试）: %s", exc)
            self.stdout.write("已注册 CMDB UUID 运行期清洗任务（异步收敛，不阻断启动）")
        except Exception as exc:
            logger.warning("注册 CMDB UUID 运行期清洗失败（不阻断启动）: %s", exc)
            self.stdout.write(self.style.WARNING(f"CMDB UUID 运行期清洗注册跳过: {exc}"))

    def _init_console_mgmt(self):
        """控制台管理资源初始化"""
        self.stdout.write("控制台管理资源初始化...")
        # 如果有控制台管理相关的初始化命令，在这里添加

    def _init_monitor(self):
        """监控资源初始化"""
        self.stdout.write("初始化监控资源...")
        call_command("plugin_init")

    def _init_node_mgmt(self):
        """节点管理初始化"""
        self.stdout.write("初始化节点管理...")
        call_command("node_init")

    def _init_alerts(self):
        """告警系统资源初始化"""
        self.stdout.write("告警系统资源初始化...")
        call_command("init_alert_sources")
        call_command("init_alert_levels")
        call_command("init_system_settings")
        call_command("init_alert_rules")
        call_command("backfill_alert_dimensions")
        call_command("backfill_event_default_team")

    def _init_operation_analysis(self):
        """运营分析系统资源初始化"""
        self.stdout.write("运营分析系统资源初始化...")
        try:
            call_command("init_default_namespace")
        except CommandError as error:
            self.stdout.write(self.style.WARNING(f"默认命名空间初始化跳过（{type(error).__name__}）: {error}"))
        call_command("init_default_groups")
        try:
            call_command("init_builtin_canvases")
        except Exception as error:
            # 内置画布/数据源是可重建的非关键资源，同步失败不应阻断服务启动。
            self.stdout.write(self.style.WARNING(f"内置画布与数据源同步跳过（{type(error).__name__}）: {error}"))

    def _init_opspilot(self):
        """OpsPilot资源初始化"""
        self.stdout.write("OpsPilot资源初始化...")
        call_command("init_llm")
        call_command("parse_tools_yml")
        call_command("init_chatflow")

    def _init_log(self):
        """日志模块初始化"""
        self.stdout.write("日志模块初始化...")
        call_command("log_init")

    def _init_mlops(self):
        """MLOPS资源初始化"""
        self.stdout.write("MLOPS资源初始化...")
        call_command("init_algorithm_config")

    def _init_patch_mgmt(self):
        """补丁管理本地内置数据初始化。"""
        self.stdout.write("补丁管理资源初始化...")
        # 权限资源已由前序 system_mgmt 初始化创建；补丁专属迁移失败必须阻断启动。
        call_command("migrate_patch_settings_split")
        try:
            call_command("init_patch_sources")
        except Exception as error:  # noqa: BLE001 - 非关键可重建数据不得阻断启动
            logger.warning("内置补丁源初始化失败，可运行 init_patch_sources 重试", exc_info=True)
            self.stdout.write(self.style.WARNING(f"内置补丁源初始化跳过（{type(error).__name__}）: {error}"))

    def _preload_language_cache(self):
        """预热语言缓存"""
        self.stdout.write("预热语言缓存...")
        try:
            result = preload_language_cache()
            self.stdout.write(self.style.SUCCESS(f"语言缓存预热完成: {len(result['loaded'])} 已加载, {len(result['skipped'])} 已跳过, {len(result['failed'])} 失败"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"语言缓存预热失败: {str(e)}"))
