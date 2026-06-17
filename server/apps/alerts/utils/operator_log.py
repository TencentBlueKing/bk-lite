# -- coding: utf-8 --
# @File: operator_log.py
# @Time: 2026/6/17
# @Author: windyzhao
"""
operator_log helper — 写入 OperatorLog 并经 NATS 镜像进平台操作日志（app=alarm）。
用法：
    from apps.alerts.utils.operator_log import record_operator_log, record_operator_logs_bulk
    record_operator_log(action=LogAction.ADD, target_type=LogTargetType.SYSTEM,
                        operator="alice", operator_object="策略-创建", target_id="5",
                        overview="创建告警分派策略[x]")
"""

from apps.alerts.constants.constants import LogAction
from apps.alerts.models.operator_log import OperatorLog
from apps.core.logger import alert_logger as logger
from apps.rpc.system_mgmt import SystemMgmt

_ACTION_MAP = {
    LogAction.ADD: "create",
    LogAction.MODIFY: "update",
    LogAction.DELETE: "delete",
    LogAction.EXECUTE: "execute",
}


def _mirror(objs):
    """将 OperatorLog 列表镜像进平台操作日志；任何异常只记录警告，不抛出。"""
    for obj in objs:
        try:
            SystemMgmt().save_operation_log(
                username=obj.operator or "system",
                source_ip="127.0.0.1",
                app="alarm",
                action_type=_ACTION_MAP.get(obj.action, "execute"),
                summary=obj.overview or "",
                target_type=obj.target_type or "",
                target_id=str(obj.target_id or ""),
                detail={"operator_object": obj.operator_object, "source": "operator_log"},
            )
        except Exception as e:  # noqa: BLE001 — 镜像失败绝不影响源写入
            logger.warning(f"mirror operator_log to operation_log failed: {e}")


def record_operator_log(**log_data):
    """写一条 OperatorLog 并镜像进平台操作日志。替代散落的 OperatorLog.objects.create(**log_data)。"""
    obj = OperatorLog.objects.create(**log_data)
    _mirror([obj])
    return obj


def record_operator_logs_bulk(items, batch_size=None):
    """
    批量写入 OperatorLog 并逐条镜像。

    :param items: List[dict | OperatorLog] — 支持字典或已构造的模型实例。
    :param batch_size: 每批写入的最大行数（None = 单批；建议大批量时传 200）。
    :return: List[OperatorLog] — 已持久化的实例列表（bulk_create 后 id 已填充）。
    """
    objs = [i if isinstance(i, OperatorLog) else OperatorLog(**i) for i in items]
    OperatorLog.objects.bulk_create(objs, batch_size=batch_size)
    _mirror(objs)
    return objs
