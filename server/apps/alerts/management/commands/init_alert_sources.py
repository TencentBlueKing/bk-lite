from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.logger import alert_logger as logger


class Command(BaseCommand):
    help = "初始化内置告警源"

    # 需要对比的字段列表（排除自动生成和不需要对比的字段）
    COMPARE_FIELDS = [
        "name",
        "source_type",
        "config",
        "access_type",
        "is_active",
        "is_effective",
        "description",
        "logo",
    ]

    def _compare_and_log_changes(self, source_id: str, old_values: dict, new_values: dict) -> dict:
        """对比新旧数据并记录变化"""
        changes = {}
        for field in self.COMPARE_FIELDS:
            old_val = old_values.get(field)
            new_val = new_values.get(field)
            if old_val != new_val:
                changes[field] = {"old": old_val, "new": new_val}
        
        if changes:
            logger.info(f"告警源 [{source_id}] 字段变更: {changes}")
            self.stdout.write(
                self.style.WARNING(f"  更新 {source_id}: {list(changes.keys())}")
            )
        return changes

    def handle(self, *args, **options):
        """初始化内置告警源"""
        logger.info("===开始初始化内置告警源===")

        try:
            from apps.alerts.constants.init_data import BUILTIN_ALERT_SOURCES
            from apps.alerts.models.alert_source import AlertSource
            
            created_count = 0
            updated_count = 0
            
            with transaction.atomic():
                for src in BUILTIN_ALERT_SOURCES:
                    source_id = src["source_id"]
                    
                    # 尝试获取已存在的告警源
                    try:
                        existing = AlertSource.all_objects.get(source_id=source_id)
                        
                        # 收集旧值
                        old_values = {
                            field: getattr(existing, field)
                            for field in self.COMPARE_FIELDS
                        }
                        
                        # 对比并记录变化
                        changes = self._compare_and_log_changes(
                            source_id, old_values, src
                        )
                        
                        # 更新字段
                        for field in self.COMPARE_FIELDS:
                            if field in src:
                                setattr(existing, field, src[field])
                        existing.save()
                        
                        if changes:
                            updated_count += 1
                        
                    except AlertSource.DoesNotExist:
                        # 创建新的告警源
                        AlertSource.all_objects.create(**src)
                        logger.info(f"创建新告警源: {source_id}")
                        self.stdout.write(
                            self.style.SUCCESS(f"  新建 {source_id}")
                        )
                        created_count += 1
            
            summary = f"成功初始化内置告警源 (新建: {created_count}, 更新: {updated_count})"
            self.stdout.write(self.style.SUCCESS(summary))
            logger.info(f"==={summary}===")

        except Exception as e:
            error_msg = f"初始化内置告警源失败: {e}"
            logger.error(error_msg, exc_info=True)
            self.stdout.write(self.style.ERROR(error_msg))
            raise
