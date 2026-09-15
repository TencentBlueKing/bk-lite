from django.core.management.base import BaseCommand, CommandError

from apps.cmdb.display_field import ExcludeFieldsCache


class Command(BaseCommand):
    help = "按需刷新 CMDB 全局字段元数据或指定模型 attrs 缓存"

    def add_arguments(self, parser):
        parser.add_argument("--model-id", default="", help="仅刷新指定模型 attrs；不传时刷新全局字段元数据")

    def handle(self, *args, **options):
        model_id = str(options.get("model_id") or "").strip()
        if model_id:
            if not ExcludeFieldsCache.refresh_model_attrs(model_id):
                raise CommandError(f"刷新 CMDB 模型 attrs 缓存失败: model_id={model_id}")
            self.stdout.write(self.style.SUCCESS(f"CMDB 模型 attrs 缓存刷新成功: model_id={model_id}"))
            return

        if not ExcludeFieldsCache.refresh_cache():
            raise CommandError("刷新 CMDB 字段元数据缓存失败")
        self.stdout.write(self.style.SUCCESS("CMDB 字段元数据缓存刷新成功"))
