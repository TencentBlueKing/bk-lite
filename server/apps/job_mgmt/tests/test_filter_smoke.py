"""目标 / 脚本过滤器冒烟测试

回归 A1 / A2：过滤器字段曾指向模型不存在的字段
（TargetFilter 的 ``source``、ScriptFilter 的 ``os_type``），
导致 ``?source=x`` / ``?os_type=x`` 在查询时触发 ``FieldError``。
本测试遍历各过滤字段并强制求值，确保查询正常执行、不抛 ``FieldError``。
"""

import pytest

from apps.job_mgmt.filters.script import ScriptFilter
from apps.job_mgmt.filters.target import TargetFilter
from apps.job_mgmt.models import Script, Target

# 每个过滤字段给一个符合查询参数格式（字符串）的样例值
TARGET_FILTER_VALUES = {
    "name": "web",
    "ip": "192.168",
    "os_type": "linux",
    "driver": "ansible",
    "node_id": "node-1",
    "cloud_region_id": "1",
    "credential_source": "manual",
    "ssh_credential_type": "password",
}

SCRIPT_FILTER_VALUES = {
    "name": "deploy",
    "script_type": "shell",
    "is_built_in": "true",
}


@pytest.mark.unit
@pytest.mark.django_db
class TestTargetFilterSmoke:
    """TargetFilter 各过滤字段冒烟：逐字段查询不抛 FieldError"""

    def test_declared_fields_match_expected(self):
        """声明的过滤字段与预期集合一致（新增字段时提醒补测）"""
        assert set(TargetFilter.base_filters) == set(TARGET_FILTER_VALUES)

    def test_source_filter_removed(self):
        """A1 回归：冗余的 source 过滤器已移除"""
        assert "source" not in TargetFilter.base_filters

    @pytest.mark.parametrize("field", list(TARGET_FILTER_VALUES))
    def test_filter_field_does_not_raise(self, field):
        """逐个过滤字段查询并强制求值，不抛 FieldError"""
        qs = TargetFilter({field: TARGET_FILTER_VALUES[field]}, queryset=Target.objects.all()).qs
        list(qs)  # 强制求值，触发查询编译/执行

    def test_all_fields_combined_does_not_raise(self):
        """所有过滤字段叠加查询，不抛 FieldError"""
        qs = TargetFilter(dict(TARGET_FILTER_VALUES), queryset=Target.objects.all()).qs
        list(qs)


@pytest.mark.unit
@pytest.mark.django_db
class TestScriptFilterSmoke:
    """ScriptFilter 各过滤字段冒烟：逐字段查询不抛 FieldError"""

    def test_declared_fields_match_expected(self):
        """声明的过滤字段与预期集合一致（新增字段时提醒补测）"""
        assert set(ScriptFilter.base_filters) == set(SCRIPT_FILTER_VALUES)

    def test_os_type_filter_removed(self):
        """A2 回归：无效的 os_type 过滤器已移除"""
        assert "os_type" not in ScriptFilter.base_filters

    @pytest.mark.parametrize("field", list(SCRIPT_FILTER_VALUES))
    def test_filter_field_does_not_raise(self, field):
        """逐个过滤字段查询并强制求值，不抛 FieldError"""
        qs = ScriptFilter({field: SCRIPT_FILTER_VALUES[field]}, queryset=Script.objects.all()).qs
        list(qs)

    def test_all_fields_combined_does_not_raise(self):
        """所有过滤字段叠加查询，不抛 FieldError"""
        qs = ScriptFilter(dict(SCRIPT_FILTER_VALUES), queryset=Script.objects.all()).qs
        list(qs)
