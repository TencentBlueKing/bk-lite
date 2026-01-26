"""
统一初始化命令 - 在单个 Python 进程中执行所有初始化任务
避免多次启动 Python 进程，大幅提升启动速度
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "批量执行初始化命令，根据 INSTALL_APPS 环境变量选择性初始化"

    def add_arguments(self, parser):
        parser.add_argument("--apps", type=str, default="", help="逗号分隔的应用列表，为空则初始化所有应用")

    def handle(self, *args, **options):
        apps = options["apps"].strip()

        # 如果为空，初始化所有应用
        if not apps:
            apps_list = ["system_mgmt", "cmdb", "monitor", "node_mgmt", "alerts", "operation_analysis", "opspilot", "log"]
        else:
            apps_list = [app.strip() for app in apps.split(",")]

        self.stdout.write(self.style.SUCCESS(f'开始批量初始化，目标模块: {", ".join(apps_list)}'))

        # 按模块执行初始化
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
                else:
                    self.stdout.write(self.style.WARNING(f"未知模块: {app}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"初始化 {app} 失败: {str(e)}"))
                # 继续执行其他模块的初始化
                continue

        self.stdout.write(self.style.SUCCESS("批量初始化完成"))

    def _init_system_mgmt(self):
        """系统管理资源初始化"""
        self.stdout.write("系统管理资源初始化...")
        call_command("init_realm_resource")
        call_command("init_login_settings")
        call_command("create_user", "admin", "password", email="admin@bklite.net", is_superuser=True)
        call_command("init_custom_menu")
        call_command("clean_group_data")

    def _init_cmdb(self):
        """CMDB资源初始化"""
        self.stdout.write("CMDB资源初始化...")
        call_command("model_init")
        call_command("init_oid")
        call_command("update_collect_task_data")
        call_command("init_field_groups")
        call_command("init_display_fields")

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
        self.stdout.write('告警系统资源初始化...')
        call_command('init_alert_sources')
        call_command('init_alert_levels')
        call_command('init_system_settings')

    def _init_operation_analysis(self):
        """运营分析系统资源初始化"""
        self.stdout.write("运营分析系统资源初始化...")
        call_command("init_default_namespace")
        call_command("init_default_groups")
        call_command("init_source_api_data", force_update=True)

    def _init_opspilot(self):
        """OpsPilot资源初始化"""
        self.stdout.write("OpsPilot资源初始化...")
        call_command("init_bot")
        call_command("init_channel")
        call_command("init_llm")
        call_command("init_provider_model")
        call_command("parse_tools_yml")
        call_command("init_chatflow")

    def _init_log(self):
        """日志模块初始化"""
        self.stdout.write("日志模块初始化...")
        call_command("log_init")
