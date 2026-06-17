"""init_builtin_canvases 管理命令覆盖测试。

对照 spec/prd/运营分析：内置画布从 YAML 导入并标记为内置只读对象。
"""

import pytest
from django.core.management import call_command

from apps.operation_analysis.models.models import Dashboard, Directory


def _ensure_default_namespace():
    from apps.operation_analysis.models.datasource_models import NameSpace

    namespace, _ = NameSpace.objects.get_or_create(
        name="默认命名空间",
        defaults={
            "domain": "127.0.0.1:4222",
            "namespace": "bklite",
            "account": "admin",
            "enable_tls": False,
            "created_by": "system",
            "updated_by": "system",
        },
    )
    namespace.set_password("test-password")
    namespace.save()
    return namespace


@pytest.mark.django_db
def test_init_builtin_canvases_creates_builtin_directory():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    call_command("init_builtin_canvases")

    # 命令应创建内置目录
    assert Directory.objects.filter(build_in_key="__builtin__").exists()


@pytest.mark.django_db
def test_init_builtin_canvases_rerun_is_idempotent():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    call_command("init_builtin_canvases")
    call_command("init_builtin_canvases")

    # 内置目录唯一
    assert Directory.objects.filter(build_in_key="__builtin__").count() == 1


@pytest.mark.django_db
def test_init_builtin_canvases_marks_existing_directory_builtin():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    # 预先存在同名根目录（非内置）
    existing = Directory.objects.create(name="内置目录", parent=None, groups=[], created_by="u")
    call_command("init_builtin_canvases")

    existing.refresh_from_db()
    assert existing.is_build_in is True
    assert existing.build_in_key == "__builtin__"


@pytest.mark.django_db
def test_init_builtin_canvases_merges_extra_yaml_files(tmp_path, settings, monkeypatch):
    from apps.operation_analysis.management.commands import init_builtin_canvases
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    base_yaml = tmp_path / "builtin_canvases.yaml"
    enterprise_yaml = tmp_path / "enterprise_builtin_canvases.yaml"
    missing_yaml = tmp_path / "missing.yaml"

    base_yaml.write_text(
        """
meta:
  schema_version: 1.0.0
dashboards:
- key: dashboard::社区内置仪表盘
  name: 社区内置仪表盘
  view_sets: []
  filters: []
datasources: []
namespaces:
- key: 默认命名空间
  name: 默认命名空间
  domain: 127.0.0.1:4222
  namespace: bklite
  account: admin
  password: test-password
  enable_tls: false
topologies: []
architectures: []
""",
        encoding="utf-8",
    )
    enterprise_yaml.write_text(
        """
meta:
  schema_version: 1.0.0
dashboards:
- key: dashboard::企业内置仪表盘
  name: 企业内置仪表盘
  view_sets: []
  filters: []
datasources: []
namespaces:
- key: 默认命名空间
  name: 默认命名空间
  domain: 127.0.0.1:4222
  namespace: bklite
  account: admin
  password: test-password
  enable_tls: false
topologies: []
architectures: []
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(init_builtin_canvases, "YAML_FILE_PATH", str(base_yaml))
    settings.OPERATION_ANALYSIS_BUILTIN_CANVAS_FILES = [str(enterprise_yaml), str(missing_yaml)]

    call_command("init_builtin_canvases")

    assert Dashboard.objects.filter(name="社区内置仪表盘", is_build_in=True).exists()
    assert Dashboard.objects.filter(name="企业内置仪表盘", is_build_in=True).exists()
