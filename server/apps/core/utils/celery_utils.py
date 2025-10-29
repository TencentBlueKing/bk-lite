import json
import time
from contextlib import contextmanager

from django.core.cache import cache
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

@contextmanager
def task_lock(lock_key, timeout=3600, blocking_timeout=0):
    """
    分布式任务锁上下文管理器，确保同一个任务同时只能有一个实例在执行

    使用Redis的SET NX操作实现分布式锁，避免同一任务并发执行。

    Args:
        lock_key: 锁的唯一标识（建议格式：task_lock:{task_name}:{unique_id}）
        timeout: 锁的过期时间（秒），防止死锁，默认3600秒（1小时）
        blocking_timeout: 等待获取锁的超时时间（秒），0表示不等待，直接失败

    Yields:
        bool: True表示成功获取锁，False表示未获取到锁

    Examples:
        # 方式1：不等待，立即返回
        with task_lock(f"task_lock:scan_policy:{policy_id}") as acquired:
            if not acquired:
                logger.warning(f"Policy {policy_id} is already running, skip")
                return
            # 执行任务逻辑
            do_something()

        # 方式2：等待最多10秒获取锁
        with task_lock(f"task_lock:scan_policy:{policy_id}", blocking_timeout=10) as acquired:
            if not acquired:
                logger.warning(f"Failed to acquire lock for policy {policy_id}")
                return
            do_something()
    """
    acquired = False
    lock_value = f"{time.time()}"  # 使用时间戳作为锁值，便于调试

    try:
        # 尝试获取锁
        start_time = time.time()
        while True:
            # cache.add() 相当于 Redis 的 SET NX，只有键不存在时才设置成功
            acquired = cache.add(lock_key, lock_value, timeout)

            if acquired:
                logger.info(f"成功获取任务锁: {lock_key}")
                break

            # 检查是否超过等待时间
            if blocking_timeout == 0:
                logger.warning(f"任务锁已被占用，跳过执行: {lock_key}")
                break

            elapsed = time.time() - start_time
            if elapsed >= blocking_timeout:
                logger.warning(f"等待任务锁超时 ({blocking_timeout}s)，跳过执行: {lock_key}")
                break

            # 短暂休眠后重试
            time.sleep(0.1)

        yield acquired

    finally:
        # 只有成功获取锁的进程才负责释放锁
        if acquired:
            try:
                # 验证锁值，确保只释放自己持有的锁
                current_value = cache.get(lock_key)
                if current_value == lock_value:
                    cache.delete(lock_key)
                    logger.info(f"成功释放任务锁: {lock_key}")
                else:
                    logger.warning(f"锁已被其他进程持有或已过期，跳过释放: {lock_key}")
            except Exception as e:
                logger.error(f"释放任务锁失败: {lock_key}, 错误: {str(e)}")
