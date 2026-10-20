"""任务行给页面看的原因：业务异常原文，其它失败只用稳定短句。"""

from __future__ import annotations

from apps.core.exceptions.base_app_exception import BaseAppException

_LIMIT = 240

_STAGE = {
    "unauthorized": "没有这条实例的操作权限",
    "missing_instance": "监控实例不存在或已删除",
    "object_mismatch": "监控对象与当前任务不一致",
    "missing_entity": "配置项不存在",
    "query_entity": "查询配置项失败",
    "query_identity": "按身份查询配置项失败",
    "bind": "写入关联失败",
    "bind_occupied": "对端已被其他实例占用",
    "bind_mismatch": "对端类型不一致或已不存在",
    "create_ci": "新建配置项失败",
    "create_ci_permission": "没有 CMDB 资产编辑权限",
    "host_missing_ip": "主机缺少 IP，无法新建",
    "missing_org": "当前组织范围内没有可用的所属组织",
    "missing_cmdb_id": "新建后没有返回配置项 ID",
    "list_candidates": "查询监控候选失败",
    "bind_cmdb_id": "写入监控关联失败",
    "backfill": "回写监控 ID 失败",
    "push": "自动关联失败",
    "identity_conflict": "身份命中多条，需要手动关联",
    "identity_not_found": "没有按身份命中对端对象",
    "host_identity_not_found": "没有按 IP+云区域命中主机",
    "platform": "平台树对象不进入本任务",
    "needs_object": "这个模型没有内置监控对象映射",
    "skipped_model": "对象不在同步名单中",
}


def safe_exc_text(exc: BaseException | None) -> str:
    if not isinstance(exc, BaseAppException):
        return ""
    text = " ".join(str(exc.message or "").split())
    return text[:_LIMIT]


def item_message(*, stage: str = "", exc: BaseException | None = None) -> str:
    text = safe_exc_text(exc)
    if text:
        return text
    return _STAGE.get(stage, "")
