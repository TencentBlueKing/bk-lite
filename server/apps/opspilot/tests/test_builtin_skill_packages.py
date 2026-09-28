"""内置技能包播种、i18n 展示、跨团队可见与删除保护。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.core.management import call_command
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.opspilot.models import SkillPackage
from apps.opspilot.serializers.llm_serializer import SkillPackageSerializer
from apps.opspilot.services.skill_package.builtin_seed import seed_all_builtin_skill_packages, seed_builtin_skill_package
from apps.opspilot.viewsets.llm_view import SkillPackageViewSet

pytestmark = pytest.mark.django_db

SUPPORT_PACKAGE = Path(__file__).resolve().parents[1] / "support-files" / "skill_packages" / "kubernetes-configuration"


def _body(resp):
    if hasattr(resp, "data"):
        return resp.data
    return json.loads(resp.content.decode("utf-8"))


def _user(*, username, locale="en", team_id=1):
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale=locale,
        group_list=[{"id": team_id, "name": f"T{team_id}"}],
        roles=["normal"],
    )
    user.is_superuser = False
    user.save()
    user.permission = {"opspilot": {"tool_list-View", "tool_list-Delete", "tool_list-Edit", "tool_list-Add"}}
    return user


@pytest.fixture
def allow_team_instances(mocker):
    mocker.patch(
        "apps.core.utils.viewset_utils.get_permission_rules",
        return_value={"instance": [], "team": [1]},
    )


def _make_mini_package(tmp_path: Path, *, name: str = "demo-k8s") -> Path:
    root = tmp_path / name
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                "description: Demo package for tests",
                "metadata:",
                '  version: "9.9.9"',
                "  domain: infrastructure",
                "  triggers: k8s, kubernetes",
                "---",
                "",
                "# Demo K8s",
                "",
                "Body text.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (root / "references").mkdir()
    (root / "references" / "workloads.md").write_text("# workloads\n", encoding="utf-8")
    return root


class TestBuiltinSkillPackageSeed:
    def test_seed_writes_extracted_and_db_row(self, tmp_path):
        source = _make_mini_package(tmp_path)
        storage_root = tmp_path / "storage"
        result = seed_builtin_skill_package(source, storage_root=storage_root)

        assert result.package_id == "demo-k8s"
        assert result.version == "9.9.9"
        assert result.created is True
        assert (result.storage_path / "extracted" / "SKILL.md").is_file()
        assert (result.storage_path / "extracted" / "references" / "workloads.md").is_file()

        pkg = SkillPackage.objects.get(package_id="demo-k8s", version="9.9.9")
        assert pkg.is_build_in is True
        assert pkg.source_type == "builtin"
        assert pkg.is_enabled is True
        assert "k8s" in pkg.triggers
        assert pkg.category == "infrastructure"

    def test_seed_is_idempotent(self, tmp_path):
        source = _make_mini_package(tmp_path)
        storage_root = tmp_path / "storage"
        first = seed_builtin_skill_package(source, storage_root=storage_root)
        second = seed_builtin_skill_package(source, storage_root=storage_root)
        assert first.created is True
        assert second.created is False
        assert SkillPackage.objects.filter(package_id="demo-k8s", version="9.9.9").count() == 1

    def test_seed_all_includes_repo_kubernetes_package(self, tmp_path):
        assert SUPPORT_PACKAGE.is_dir(), "support-files kubernetes-configuration 缺失"
        storage_root = tmp_path / "storage"
        results = seed_all_builtin_skill_packages(
            support_root=SUPPORT_PACKAGE.parent,
            storage_root=storage_root,
        )
        ids = {item.package_id for item in results}
        assert "kubernetes-configuration" in ids
        pkg = SkillPackage.objects.get(package_id="kubernetes-configuration", is_build_in=True)
        assert pkg.version == "1.1.1"
        assert (Path(pkg.storage_path) / "extracted" / "SKILL.md").is_file()

    def test_init_skill_packages_command(self, tmp_path, mocker):
        storage_root = tmp_path / "storage"
        mocker.patch(
            "apps.opspilot.services.skill_package.builtin_seed.DEFAULT_SKILL_PACKAGE_ROOT",
            storage_root,
        )
        mocker.patch(
            "apps.opspilot.services.skill_package.builtin_seed.DEFAULT_SUPPORT_ROOT",
            SUPPORT_PACKAGE.parent,
        )
        call_command("init_skill_packages")
        assert SkillPackage.objects.filter(package_id="kubernetes-configuration", is_build_in=True).exists()


class TestSkillPackageSerializerI18n:
    def test_display_fields_prefer_language_yaml(self, mocker):
        mocker.patch(
            "apps.core.utils.serializers.get_permission_rules",
            return_value={"instance": [], "team": [1]},
        )
        pkg = SkillPackage.objects.create(
            package_id="kubernetes-configuration",
            name="kubernetes-configuration",
            version="1.1.1",
            description="raw-en-description",
            domain="domain.com",
            is_build_in=True,
            source_type="builtin",
        )
        zh_user = _user(username="pkg_zh", locale="zh-Hans")
        en_user = _user(username="pkg_en", locale="en")
        factory = APIRequestFactory()
        zh_request = factory.get("/")
        zh_request.user = zh_user
        en_request = factory.get("/")
        en_request.user = en_user
        zh_data = SkillPackageSerializer(pkg, context={"request": zh_request}).data
        en_data = SkillPackageSerializer(pkg, context={"request": en_request}).data
        assert zh_data["display_name"] == "Kubernetes 配置"
        assert "Kubernetes" in zh_data["description_tr"]
        assert en_data["display_name"] == "Kubernetes Configuration"
        assert "Kubernetes" in en_data["description_tr"]

    def test_display_fields_fallback_to_db(self, mocker):
        mocker.patch(
            "apps.core.utils.serializers.get_permission_rules",
            return_value={"instance": [], "team": [1]},
        )
        pkg = SkillPackage.objects.create(
            package_id="custom-no-i18n",
            name="Custom Pack",
            version="0.1.0",
            description="Custom description",
            domain="domain.com",
        )
        user = _user(username="pkg_fb", locale="zh-Hans")
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = user
        data = SkillPackageSerializer(pkg, context={"request": request}).data
        assert data["display_name"] == "Custom Pack"
        assert data["description_tr"] == "Custom description"


class TestBuiltinSkillPackageVisibilityAndDelete:
    def test_builtin_visible_even_when_team_empty(self, allow_team_instances):
        SkillPackage.objects.create(
            package_id="kubernetes-configuration",
            name="Kubernetes Specialist",
            version="1.1.1",
            description="desc",
            domain="domain.com",
            team=[],
            is_build_in=True,
            source_type="builtin",
            is_enabled=True,
        )
        SkillPackage.objects.create(
            package_id="team-only",
            name="Team Only",
            version="0.1.0",
            description="private",
            domain="domain.com",
            team=[99],
            is_build_in=False,
            is_enabled=True,
        )
        user = _user(username="pkg_vis")
        factory = APIRequestFactory()
        request = factory.get("/")
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        resp = SkillPackageViewSet.as_view({"get": "list"})(request)
        assert resp.status_code == 200
        payload = _body(resp)
        items = payload if isinstance(payload, list) else payload.get("items") or payload.get("results") or []
        package_ids = {item["package_id"] for item in items}
        assert "kubernetes-configuration" in package_ids
        assert "team-only" not in package_ids

    def test_destroy_builtin_rejected(self, allow_team_instances):
        pkg = SkillPackage.objects.create(
            package_id="kubernetes-configuration",
            name="Kubernetes Specialist",
            version="1.1.1",
            description="desc",
            domain="domain.com",
            team=[],
            is_build_in=True,
            source_type="builtin",
        )
        user = _user(username="pkg_del")
        factory = APIRequestFactory()
        request = factory.delete("/")
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        resp = SkillPackageViewSet.as_view({"delete": "destroy"})(request, pk=pkg.id)
        assert resp.status_code == 400
        assert _body(resp).get("result") is False
        assert SkillPackage.objects.filter(id=pkg.id).exists()
