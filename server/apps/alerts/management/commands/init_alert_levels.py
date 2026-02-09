from django.core.management.base import BaseCommand
from apps.core.logger import alert_logger as logger


class Command(BaseCommand):
    help = "初始化告警级别"

    def handle(self, *args, **options):
        """初始化告警级别"""
        logger.info("===开始初始化告警级别===")
        
        try:
            from apps.alerts.constants.init_data import DEFAULT_LEVEL
            from apps.alerts.models.models import Level
            
            created_count = 0
            for level_data in DEFAULT_LEVEL:
                level_data["built_in"] = True
                _, created = Level.objects.get_or_create(
                    level_type=level_data["level_type"], 
                    level_id=level_data["level_id"],
                    level_name=level_data["level_name"],
                    defaults=level_data
                )
                if created:
                    created_count += 1
            
            self.stdout.write(
                self.style.SUCCESS(f'成功初始化 {created_count} 个告警级别')
            )
            logger.info(f"===成功初始化 {created_count} 个告警级别===")
            
        except Exception as e:
            error_msg = f"初始化告警级别失败: {e}"
            logger.error(error_msg)
            self.stdout.write(self.style.ERROR(error_msg))
            raise
