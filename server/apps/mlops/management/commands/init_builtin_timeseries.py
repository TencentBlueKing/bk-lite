from django.core.management.base import BaseCommand

from apps.mlops.services.builtin_timeseries import ensure_builtin_timeseries_records


class Command(BaseCommand):
    help = "在预置时序容器已部署时，幂等写入内置训练任务和发布记录"

    def handle(self, *args, **options):
        result = ensure_builtin_timeseries_records()
        if result["skipped"]:
            self.stdout.write("未配置预置时序服务地址，跳过内置记录")
            return
        self.stdout.write(
            "预置时序记录已对齐："
            f"新建训练任务 {result['created_train_jobs']}，新建发布 {result['created_servings']}"
        )
