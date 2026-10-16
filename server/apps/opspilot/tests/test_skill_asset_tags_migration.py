"""0086：内置工具/技能包 system_tags 在首次 migrate 时回填。"""

import importlib

import pytest
from django.apps import apps

from apps.opspilot.models import SkillPackage, SkillTools

migration_0086 = importlib.import_module("apps.opspilot.migrations.0086_skill_asset_tags")

pytestmark = pytest.mark.django_db


def test_migration_0086_backfills_builtin_system_tags():
    SkillTools.objects.create(
        name="postgres",
        description="PostgreSQL",
        is_build_in=True,
        team=[1],
        domain="domain.com",
        tags=["legacy"],
        system_tags=[],
        user_tags=[],
        params={"url": "langchain:postgres", "name": "postgres", "kwargs": []},
    )
    SkillTools.objects.create(
        name="custom-mcp-migration-demo",
        description="MCP",
        is_build_in=False,
        team=[1],
        domain="domain.com",
        tags=["ops", "db"],
        system_tags=["stale"],
        user_tags=[],
        params={"url": "mcp:custom", "name": "custom-mcp-migration-demo", "kwargs": []},
    )
    SkillPackage.objects.create(
        package_id="demo-package-migration",
        version="1.0.0",
        name="Demo",
        description="",
        is_build_in=True,
        team=[1],
        domain="domain.com",
        manifest={"system_tags": ["monitoring_alert", "platform_app"]},
        category="",
        system_tags=[],
        user_tags=[],
    )

    migration_0086.copy_mcp_tags_to_user_tags(apps, None)

    builtin_tool = SkillTools.objects.get(name="postgres", is_build_in=True)
    custom_tool = SkillTools.objects.get(name="custom-mcp-migration-demo", is_build_in=False)
    builtin_package = SkillPackage.objects.get(package_id="demo-package-migration", is_build_in=True)

    assert builtin_tool.system_tags == ["database"]
    assert custom_tool.user_tags == ["ops", "db"]
    assert custom_tool.system_tags == []
    assert builtin_package.system_tags == ["monitoring_alert", "platform_app"]
