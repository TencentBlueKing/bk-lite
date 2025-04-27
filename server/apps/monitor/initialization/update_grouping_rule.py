from django_celery_beat.models import PeriodicTask, IntervalSchedule


def create_periodic_task(sender, **kwargs):
    # 定义任务的时间间隔，例如每10分钟执行一次
    schedule, created = IntervalSchedule.objects.get_or_create(
        every=10,  # 每10分钟
        period=IntervalSchedule.MINUTES,  # 单位是分钟
    )
    # 如果不存在就创建一个新的定时任务，否则不创建
    PeriodicTask.objects.get_or_create(
        name="sync_instance_and_group",  # 任务名称
        task="apps.monitor.tasks.grouping_rule.sync_instance_and_group",  # 任务函数
        interval=schedule,  # 时间间隔
    )
