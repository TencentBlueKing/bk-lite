"""patch_mgmt 测试框架与配置发现测试（Todo 3）。

与 Todo 2 的 test_models.py 互不重叠：
  - test_models.py  → schema 行为（约束、关系、状态守卫）
  - test_harness.py → 框架/配置/发现（导入、注册、Celery 路径、表存在性）

测试分层：
  1. 纯导入冒烟（无 DB）：所有关键模块可无副作用导入。
  2. Django AppConfig 注册（无 DB）：AppRegistry 解析正确。
  3. Celery Beat 发现路径（无 DB）：复现 config/components/celery.py 逻辑。
  4. Schema 表存在性（需 DB）：Todo 2 迁移后关键表可查。
"""

import importlib

import pytest
from django.apps import apps as django_apps
from django.db import connection


# ── 1. 纯导入冒烟测试 ────────────────────────────────────────────────────────

class TestPatchMgmtImports:
    """关键模块均可无副作用导入。"""

    def test_models_importable(self):
        mod = importlib.import_module("apps.patch_mgmt.models")
        assert hasattr(mod, "Patch")
        assert hasattr(mod, "PatchTarget")
        assert hasattr(mod, "PatchSource")

    def test_patch_package_model_is_not_exported(self):
        mod = importlib.import_module("apps.patch_mgmt.models")
        assert not hasattr(mod, "PatchPackage")

    def test_constants_importable(self):
        mod = importlib.import_module("apps.patch_mgmt.constants")
        assert hasattr(mod, "OSType")
        assert hasattr(mod, "RebootPolicy")
        assert hasattr(mod, "PatchSourceType")

    def test_catalog_source_type_is_removed(self):
        from apps.patch_mgmt.constants import PatchSourceType

        assert not hasattr(PatchSourceType, "WINDOWS_CATALOG")
        assert "windows_catalog" not in {value for value, _ in PatchSourceType.CHOICES}

    def test_upload_required_package_status_is_removed(self):
        from apps.patch_mgmt.constants import PackageStatus

        assert not hasattr(PackageStatus, "UPLOAD_REQUIRED")
        assert "upload_required" not in {value for value, _ in PackageStatus.CHOICES}

    def test_config_importable(self):
        mod = importlib.import_module("apps.patch_mgmt.config")
        assert hasattr(mod, "CELERY_BEAT_SCHEDULE")

    def test_apps_config_importable(self):
        mod = importlib.import_module("apps.patch_mgmt.apps")
        assert hasattr(mod, "PatchMgmtConfig")


# ── 2. Django AppConfig 注册 ─────────────────────────────────────────────────

class TestPatchMgmtAppConfig:
    """PatchMgmtConfig 在 AppRegistry 中注册正确。"""

    def test_app_config_registered(self):
        # Raises LookupError if not installed — proves INSTALL_APPS wiring works
        config = django_apps.get_app_config("patch_mgmt")
        assert config.name == "apps.patch_mgmt"

    def test_app_verbose_name(self):
        config = django_apps.get_app_config("patch_mgmt")
        assert config.verbose_name == "补丁管理"

    def test_app_label(self):
        config = django_apps.get_app_config("patch_mgmt")
        assert config.label == "patch_mgmt"

    def test_models_registered_in_app(self):
        """AppRegistry 能从 patch_mgmt 枚举所有已注册模型。"""
        config = django_apps.get_app_config("patch_mgmt")
        model_names = {m.__name__ for m in config.get_models()}
        expected = {
            "Patch", "PatchTarget", "PatchSource",
            "WindowsPatchDetail", "LinuxPatchDetail",
        }
        missing = expected - model_names
        assert not missing, f"Models not registered in app: {missing}"


# ── 3. Celery Beat 配置发现路径 ──────────────────────────────────────────────

class TestCeleryBeatScheduleDiscovery:
    """config.py 中的 CELERY_BEAT_SCHEDULE 可被 celery.py 自动发现逻辑解析。

    复现 config/components/celery.py 中的发现逻辑：
        for app_label in INSTALLED_APPS:
            config_module = f"{app_label}.config"
            mod = importlib.import_module(config_module)
            app_schedule = getattr(mod, "CELERY_BEAT_SCHEDULE", None)
    """

    def test_schedule_is_dict(self):
        mod = importlib.import_module("apps.patch_mgmt.config")
        schedule = getattr(mod, "CELERY_BEAT_SCHEDULE", None)
        assert isinstance(schedule, dict), (
            "CELERY_BEAT_SCHEDULE must be a dict so celery.py can call .update()"
        )

    def test_discovery_module_path_matches_app_name(self):
        """celery.py 用 f'{app_label}.config'；app_label 来自 INSTALLED_APPS 条目。"""
        config = django_apps.get_app_config("patch_mgmt")
        # INSTALLED_APPS 条目为 "apps.patch_mgmt"，故 config_module = "apps.patch_mgmt.config"
        expected_module = f"{config.name}.config"
        mod = importlib.import_module(expected_module)
        assert hasattr(mod, "CELERY_BEAT_SCHEDULE")

    def test_schedule_entries_structurally_valid(self):
        """若 MVP 后有任何调度条目，每条须包含 task 和 schedule 键。"""
        mod = importlib.import_module("apps.patch_mgmt.config")
        for name, entry in mod.CELERY_BEAT_SCHEDULE.items():
            assert "task" in entry, f"Entry '{name}' missing 'task' key"
            assert "schedule" in entry, f"Entry '{name}' missing 'schedule' key"

# ── 4. Schema 表存在性（依赖 Todo 2 迁移） ───────────────────────────────────

@pytest.mark.django_db
class TestPatchMgmtSchemaTables:
    """migrate 后，patch_mgmt_* 表在测试数据库中可见。"""

    def test_core_tables_exist(self):
        app_config = django_apps.get_app_config("patch_mgmt")
        expected = {m._meta.db_table for m in app_config.get_models()}
        with connection.cursor() as cursor:
            available = {ti.name for ti in connection.introspection.get_table_list(cursor)}
        missing = expected - available
        assert not missing, (
            f"Tables missing after migrations (run 'make migrate'): {sorted(missing)}"
        )

    def test_models_queryable_against_empty_db(self):
        """无需行数据；queryset 求值本身证明表可访问。"""
        from apps.patch_mgmt.models import (
            Patch,
            PatchSource,
            PatchTarget,
        )
        assert Patch.objects.count() == 0
        assert PatchTarget.objects.count() == 0
        assert PatchSource.objects.count() == 0
