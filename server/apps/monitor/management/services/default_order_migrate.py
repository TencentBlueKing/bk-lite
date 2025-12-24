from apps.monitor.constants.database import DatabaseConstants
from apps.core.logger import monitor_logger as logger


def migrate_default_order():
    """
    初始化默认排序。

    只初始化 order=999（默认值）的分类和对象。

    优化：使用 bulk_update 批量更新
    """
    try:
        from django.db import transaction
        from apps.monitor.constants.monitor_object import MonitorObjConstants
        from apps.monitor.models import MonitorObjectType, MonitorObject

        with transaction.atomic():
            # 找出所有需要初始化的分类（order=999）
            uninit_types = set(MonitorObjectType.objects.filter(order=999).values_list('id', flat=True))

            # 找出所有需要初始化的对象（order=999）
            uninit_objects = {obj.id: obj for obj in MonitorObject.objects.filter(order=999).select_related('type')}

            type_updates = []
            object_updates = []

            # 遍历默认顺序配置
            for idx, item in enumerate(MonitorObjConstants.DEFAULT_OBJ_ORDER):
                type_id = item.get("type")
                name_list = item.get("name_list", [])

                # 如果该分类需要初始化
                if type_id in uninit_types:
                    obj_type, created = MonitorObjectType.objects.get_or_create(
                        id=type_id,
                        defaults={'order': idx}
                    )
                    if not created and obj_type.order == 999:
                        obj_type.order = idx
                        type_updates.append(obj_type)

                # 初始化该分类下需要初始化的对象
                for name_idx, name in enumerate(name_list):
                    for obj_id, obj in uninit_objects.items():
                        if obj.name == name and obj.type_id == type_id:
                            obj.order = name_idx
                            object_updates.append(obj)

            # 批量更新分类顺序
            if type_updates:
                MonitorObjectType.objects.bulk_update(
                    type_updates,
                    ['order'],
                    batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE
                )
                logger.info(f'批量更新分类顺序: {len(type_updates)} 个')

            # 批量更新对象顺序
            if object_updates:
                MonitorObject.objects.bulk_update(
                    object_updates,
                    ['order'],
                    batch_size=DatabaseConstants.MONITOR_OBJECT_BATCH_SIZE
                )
                logger.info(f'批量更新对象顺序: {len(object_updates)} 个')

        logger.info('默认顺序初始化完成')

    except Exception as e:
        logger.error(f'初始化默认顺序失败: {e}')
        import traceback
        logger.error(traceback.format_exc())
