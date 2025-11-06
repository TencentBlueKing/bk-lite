import json
from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask
from apps.core.logger import opspilot_logger as logger


def crontab_format(value_type: str, value: str):
    """将数据转换成crontab格式"""
    is_interval = True
    if value_type == "cycle":
        scan_cycle = "*/{} * * * *".format(int(value))
    elif value_type == "timing":
        time_data = value.split(":")
        if len(time_data) != 2:
            raise Exception("定时时间格式错误！")
        scan_cycle = "{} {} * * *".format(int(time_data[1]), int(time_data[0]))
    elif value_type == "close":
        scan_cycle = ""
        is_interval = False
    else:
        raise Exception("定时类型错误！")
    return is_interval, scan_cycle


class CeleryUtils:
    @staticmethod
    def create_or_update_periodic_task(name, crontab=None, interval=None, task=None, args=None, kwargs=None,
                                       enabled=True):
        """
        创建或更新周期任务
        """
        logger.info(f"创建或更新周期任务: name={name}, crontab={crontab}, interval={interval}, task={task}, enabled={enabled}")
        
        if crontab:
            minute, hour, day_of_month, month_of_year, day_of_week = crontab.split()
            schedule_data = dict(
                minute=minute,
                hour=hour,
                day_of_month=day_of_month,
                month_of_year=month_of_year,
                day_of_week=day_of_week,
            )
            schedule, created = CrontabSchedule.objects.get_or_create(**schedule_data, defaults=schedule_data)
            schedule_type = "crontab"
        elif interval:
            schedule_data = dict(every=interval, period='seconds')
            schedule, created = IntervalSchedule.objects.get_or_create(**schedule_data, defaults=schedule_data)
            schedule_type = "interval"
        else:
            raise ValueError('Either crontab or interval must be provided')

        defaults = dict(
            task=task,
            args=json.dumps(args) if args else '[]',
            kwargs=json.dumps(kwargs) if kwargs else '{}',
            enabled=enabled,
        )
        
        if schedule_type == "crontab":
            defaults['crontab'] = schedule
            defaults['interval'] = None
        else:
            defaults['interval'] = schedule
            defaults['crontab'] = None

        task_obj, task_created = PeriodicTask.objects.update_or_create(name=name, defaults=defaults)
        
        action = "创建" if task_created else "更新"
        logger.info(f"{action}周期任务成功: {name}")
        
        return task_obj

    @staticmethod
    def delete_periodic_task(name):
        """
        删除周期任务
        """
        try:
            deleted_count, _ = PeriodicTask.objects.filter(name=name).delete()
            if deleted_count > 0:
                logger.info(f"删除周期任务成功: {name}")
            else:
                logger.warning(f"未找到要删除的周期任务: {name}")
            return deleted_count
        except Exception as e:
            logger.error(f"删除周期任务失败: {name}, 错误: {str(e)}")
            raise

    @staticmethod
    def get_periodic_task(name):
        """
        获取周期任务
        :param name: 任务名称
        :return: 任务对象，如果不存在则返回None
        """
        try:
            return PeriodicTask.objects.get(name=name)
        except PeriodicTask.DoesNotExist:
            return None

    @staticmethod
    def get_all_periodic_tasks():
        """
        获取所有周期任务
        :return: 所有周期任务的查询集
        """
        return PeriodicTask.objects.all()

    @staticmethod
    def enable_periodic_task(name):
        """
        启用周期任务
        :param name: 任务名称
        """
        try:
            task = PeriodicTask.objects.get(name=name)
            task.enabled = True
            task.save()
            logger.info(f"启用周期任务成功: {name}")
            return True
        except PeriodicTask.DoesNotExist:
            logger.warning(f"要启用的周期任务不存在: {name}")
            return False
        except Exception as e:
            logger.error(f"启用周期任务失败: {name}, 错误: {str(e)}")
            raise

    @staticmethod
    def disable_periodic_task(name):
        """
        禁用周期任务
        :param name: 任务名称
        """
        try:
            task = PeriodicTask.objects.get(name=name)
            task.enabled = False
            task.save()
            logger.info(f"禁用周期任务成功: {name}")
            return True
        except PeriodicTask.DoesNotExist:
            logger.warning(f"要禁用的周期任务不存在: {name}")
            return False
        except Exception as e:
            logger.error(f"禁用周期任务失败: {name}, 错误: {str(e)}")
            raise

    @staticmethod
    def is_task_enabled(name):
        """
        检查任务是否启用
        :param name: 任务名称
        :return: True/False 或 None（任务不存在）
        """
        try:
            task = PeriodicTask.objects.get(name=name)
            return task.enabled
        except PeriodicTask.DoesNotExist:
            return None
