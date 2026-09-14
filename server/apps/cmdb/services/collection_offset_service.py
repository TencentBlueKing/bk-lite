"""任务保存时的错峰编排；纯分配与配置渲染不承担数据库协调。"""
from contextlib import nullcontext

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.collection_offset import CollectionSchedule, assign_offset, occupancy_width_minutes
from apps.cmdb.services.collection_offset_policy import active_channels, effective_offset_seconds, supported_model_ids, supports_task, target_count
from apps.cmdb.services.unique_write_lock import UniqueWriteLockService


class CollectionOffsetService:
    LOCK_KEY = "cmdb:collection-offset"

    @classmethod
    def serialize(cls, task, *, data=None):
        # 必须在调用方的保存事务内持有，提交前释放；唯一键写锁覆盖至事务结束。
        if supports_task(task) or (data is not None and supports_task(data)):
            return UniqueWriteLockService.hold([cls.LOCK_KEY])
        return nullcontext()

    @classmethod
    def apply(cls, instance, *, previous=None) -> None:
        channels = active_channels(instance)
        if not channels:
            return
        old_params = dict(previous.params or {}) if previous is not None else {}
        # 没有服务端偏移的存量任务不因编辑自动加入错峰。
        if previous is not None and not any(channel.offset_key in old_params for channel, _ in channels):
            return
        previous_channels = {channel.role: cycle for channel, cycle in active_channels(previous)} if previous is not None else {}
        params = dict(instance.params or {})
        changed_roles = {
            channel.role
            for channel, cycle in channels
            if previous is None
            or channel.offset_key not in old_params
            or previous_channels.get(channel.role) != cycle
            or previous.access_point != instance.access_point
        }
        if not changed_roles:
            return
        existing = []
        tasks = (
            CollectModels.objects.filter(model_id__in=supported_model_ids(), is_interval=True, cycle_value_type="cycle")
            .exclude(pk=instance.pk)
            .only("id", "model_id", "is_interval", "cycle_value_type", "cycle_value", "params", "instances", "ip_range")
        )
        for task in tasks.iterator(chunk_size=200):
            count = target_count(task)
            for channel, cycle in active_channels(task):
                existing.append(cls._schedule(task.id, channel, cycle, count, task.params))
        count = target_count(instance)
        # 未改通道同样占位，不能因编辑另一条通道而遗漏自己。
        for channel, cycle in channels:
            if channel.role not in changed_roles:
                existing.append(cls._schedule(instance.id, channel, cycle, count, params))
        for channel, cycle in channels:
            if channel.role not in changed_roles:
                continue
            raw_offset = old_params.get(channel.offset_key)
            preferred = effective_offset_seconds(raw_offset, cycle * 60)
            preferred = preferred // 60 if raw_offset == preferred and preferred % 60 == 0 else None
            schedule = assign_offset(
                task_id=instance.id,
                cycle_minutes=cycle,
                target_count=count,
                existing=existing,
                preferred_offset_minutes=preferred,
                channel=channel.role,
            )
            params[channel.offset_key] = schedule.collection_offset_seconds
            existing.append(schedule)
        instance.params = params
        instance.save(update_fields=["params"])

    @staticmethod
    def _schedule(task_id, channel, cycle, count, params):
        return CollectionSchedule(
            task_id=task_id,
            cycle_minutes=cycle,
            target_count=count,
            offset_minutes=effective_offset_seconds((params or {}).get(channel.offset_key), cycle * 60) // 60,
            width_minutes=occupancy_width_minutes(count, cycle),
        )
