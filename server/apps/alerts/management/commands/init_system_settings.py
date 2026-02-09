from django.core.management.base import BaseCommand
from apps.core.logger import alert_logger as logger


class Command(BaseCommand):
    help = "初始化系统设置"

    def handle(self, *args, **options):
        """初始化系统设置"""
        logger.info("===开始初始化系统设置===")
        
        try:
            from apps.alerts.constants.init_data import SYSTEM_SETTINGS
            from apps.alerts.models.sys_setting import SystemSetting
            
            created_count = 0
            for data in SYSTEM_SETTINGS:
                _, created = SystemSetting.objects.get_or_create(
                    key=data["key"],
                    defaults=data
                )
                if created:
                    created_count += 1
            
            self.stdout.write(
                self.style.SUCCESS(f'成功初始化 {created_count} 个系统设置')
            )
            logger.info(f"===成功初始化 {created_count} 个系统设置===")
            
        except Exception as e:
            error_msg = f"初始化系统设置失败: {e}"
            logger.error(error_msg)
            self.stdout.write(self.style.ERROR(error_msg))
            raise
