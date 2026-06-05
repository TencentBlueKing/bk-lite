"""init_builtin_canvases 管理命令覆盖测试。

对照 spec/prd/运营分析：内置画布从 YAML 导入并标记为内置只读对象。
"""

import pytest
from django.core.management import call_command

from apps.operation_analysis.models.models import Directory


@pytest.mark.django_db
def test_init_builtin_canvases_creates_builtin_directory():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    call_command("init_builtin_canvases")

    # 命令应创建内置目录
    assert Directory.objects.filter(build_in_key="__builtin__").exists()


@pytest.mark.django_db
def test_init_builtin_canvases_rerun_is_idempotent():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    call_command("init_builtin_canvases")
    call_command("init_builtin_canvases")

    # 内置目录唯一
    assert Directory.objects.filter(build_in_key="__builtin__").count() == 1


@pytest.mark.django_db
def test_init_builtin_canvases_marks_existing_directory_builtin():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    # 预先存在同名根目录（非内置）
    existing = Directory.objects.create(name="内置目录", parent=None, groups=[], created_by="u")
    call_command("init_builtin_canvases")

    existing.refresh_from_db()
    assert existing.is_build_in is True
    assert existing.build_in_key == "__builtin__"
