"""选项来源身份解析。

本地权威是数据源主键。名称和 rest_api 只是展示，不参与否决。
build_in_key 只在主键已经不存在时恢复内置逻辑身份。
旧 sourceRef 按全表候选数判断，不用调用方看得见的子集。
"""

from __future__ import annotations

from django.db.models import CharField, Q, Value
from django.db.models.functions import Concat

from apps.operation_analysis.common.datasource_visibility import can_access_datasource_in_org
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel

RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
MISSING = "missing"
FORBIDDEN = "forbidden"


def _result(status, source_id=None):
    payload = {"status": status}
    if status == RESOLVED and source_id is not None:
        payload["id"] = source_id
    return payload


def _accessible(row, current_team, *, is_superuser):
    # 与 get_source_data 同一套组织判断。超级用户不能把别的组织解析成可用，
    # 否则解析成功后取数仍是 403，前端只会弹全局提示。
    del is_superuser
    return can_access_datasource_in_org(row, current_team)


def _legacy_queryset(value):
    named = DataSourceAPIModel.objects.annotate(
        display_key=Concat("name", Value("::"), "rest_api", output_field=CharField()),
    ).filter(Q(build_in_key=value) | (Q(display_key=value) & ~Q(name="")))
    if named.exists():
        return named
    return DataSourceAPIModel.objects.filter(rest_api=value)


def resolve_option_source(
    *,
    source_id=None,
    builtin_key=None,
    source_ref=None,
    current_team=None,
    is_superuser=False,
):
    """返回 resolved / ambiguous / missing / forbidden。不附带候选名称。"""
    if source_id is not None:
        row = DataSourceAPIModel.objects.filter(pk=source_id).first()
        if row is not None:
            if not _accessible(row, current_team, is_superuser=is_superuser):
                return _result(FORBIDDEN)
            return _result(RESOLVED, row.pk)
        restored = _restore_builtin(builtin_key, current_team, is_superuser)
        if restored is not None:
            return restored
        return _result(MISSING)

    if builtin_key:
        restored = _restore_builtin(builtin_key, current_team, is_superuser)
        if restored is not None:
            return restored

    ref = source_ref if isinstance(source_ref, str) else ""
    ref = ref.strip()
    if not ref:
        return _result(MISSING)
    rows = list(_legacy_queryset(ref).distinct())
    if len(rows) == 0:
        return _result(MISSING)
    if len(rows) > 1:
        return _result(AMBIGUOUS)
    row = rows[0]
    if not _accessible(row, current_team, is_superuser=is_superuser):
        return _result(FORBIDDEN)
    return _result(RESOLVED, row.pk)


def _restore_builtin(builtin_key, current_team, is_superuser):
    key = (builtin_key or "").strip()
    if not key:
        return None
    rows = list(DataSourceAPIModel.objects.filter(build_in_key=key, is_build_in=True))
    if len(rows) == 0:
        return None
    if len(rows) > 1:
        return _result(AMBIGUOUS)
    row = rows[0]
    if not _accessible(row, current_team, is_superuser=is_superuser):
        return _result(FORBIDDEN)
    return _result(RESOLVED, row.pk)
