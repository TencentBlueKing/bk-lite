"""内置技能包与内置工具的播种、可见性与删除保护。"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.opspilot.models import LLMSkill, SkillPackage, SkillTools
from apps.opspilot.serializers.llm_serializer import SkillPackageSerializer
from apps.opspilot.services.skill_package.builtin_seed import seed_all_builtin_skill_packages, seed_builtin_skill_package
from apps.opspilot.services.skill_package.importer import SkillPackageImporter
from apps.opspilot.viewsets.llm_view import SkillPackageViewSet, SkillToolsViewSet
from apps.system_mgmt.models.user import Group

pytestmark = pytest.mark.django_db

SUPPORT_PACKAGE = Path(__file__).resolve().parents[1] / "support-files" / "skill_packages" / "kubernetes-configuration"


def _body(resp):
    if hasattr(resp, "data"):
        return resp.data
    return json.loads(resp.content.decode("utf-8"))


def _user(*, username, locale="en", team_id=1, domain="domain.com"):
    user = User.objects.create_user(
        username=username,
        password="x",
        domain=domain,
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
        pkg = SkillPackage.objects.get(package_id="demo-k8s")
        assert pkg.system_tags == []
        assert pkg.category == "infrastructure"

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
        assert pkg.system_tags == ["container"]
        assert pkg.user_tags == []
        assert pkg.category != "container"
        default_group = Group.objects.filter(name="Default", parent_id=0).only("id").first()
        assert pkg.team == ([default_group.id] if default_group else [1])
        assert (Path(pkg.storage_path) / "extracted" / "SKILL.md").is_file()

        pkg.user_tags = ["值班"]
        pkg.system_tags = ["stale"]
        pkg.team = [99]
        pkg.save(update_fields=["user_tags", "system_tags", "team"])
        seed_all_builtin_skill_packages(
            support_root=SUPPORT_PACKAGE.parent,
            storage_root=storage_root,
        )
        pkg.refresh_from_db()
        assert pkg.system_tags == ["container"]
        assert pkg.user_tags == ["值班"]
        assert pkg.team == [99]
        assert pkg.category != "container"

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

    def test_ppt_master_display_fields_use_language_yaml(self, mocker):
        mocker.patch(
            "apps.core.utils.serializers.get_permission_rules",
            return_value={"instance": [], "team": [1]},
        )
        pkg = SkillPackage.objects.create(
            package_id="ppt-master",
            name="PPT Master Skill",
            version="6.7.2",
            description="AI-driven presentation workflow for generating editable PPTX decks and slides",
            domain="domain.com",
            is_build_in=True,
            source_type="builtin",
        )
        factory = APIRequestFactory()
        zh_request = factory.get("/")
        zh_request.user = _user(username="ppt_pkg_zh", locale="zh-Hans")
        en_request = factory.get("/")
        en_request.user = _user(username="ppt_pkg_en", locale="en")
        zh_data = SkillPackageSerializer(pkg, context={"request": zh_request}).data
        en_data = SkillPackageSerializer(pkg, context={"request": en_request}).data
        assert zh_data["display_name"] == "PPT Master"
        assert "演示文稿" in zh_data["description_tr"]
        assert "AI-driven" not in zh_data["description_tr"]
        assert en_data["display_name"] == "PPT Master"
        assert "native PPTX" in en_data["description_tr"]

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
            package_id="caller-team",
            name="Caller Team",
            version="0.1.0",
            description="mine",
            domain="domain.com",
            team=[1],
            is_build_in=False,
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
        assert "caller-team" in package_ids
        assert "team-only" in package_ids

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


def _listed_packages(user, team_id):
    factory = APIRequestFactory()
    request = factory.get("/")
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = str(team_id)
    resp = SkillPackageViewSet.as_view({"get": "list"})(request)
    assert resp.status_code == 200
    payload = _body(resp)
    items = payload if isinstance(payload, list) else payload.get("items") or payload.get("results") or []
    return items


def _skill_zip(package_id, version, description):
    body = "\n".join(
        [
            "---",
            f"id: {package_id}",
            "name: Shared Skill",
            f"version: {version}",
            f"description: {description}",
            "---",
            "",
            "# Shared Skill",
            "",
            "## Runtime",
            "",
            "- command: echo ok",
            "",
        ]
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{package_id}/SKILL.md", body)
    buffer.seek(0)
    return buffer


class TestSharedSkillPackageCatalog:
    def test_other_domain_package_stays_hidden(self, allow_team_instances):
        SkillPackage.objects.create(
            package_id="other-domain",
            name="Other Domain",
            version="0.1.0",
            description="hidden",
            domain="other.example",
            team=[1],
            is_enabled=True,
        )
        user = _user(username="pkg_domain")
        package_ids = {item["package_id"] for item in _listed_packages(user, 1)}
        assert "other-domain" not in package_ids

    def test_other_group_can_edit_tags_without_adopting_team(self, allow_team_instances):
        pkg = SkillPackage.objects.create(
            package_id="shared-edit",
            name="Shared Edit",
            version="0.1.0",
            description="editable",
            domain="domain.com",
            team=[1],
            user_tags=[],
            is_enabled=True,
        )
        user = _user(username="pkg_edit", team_id=2)
        factory = APIRequestFactory()
        request = factory.patch("/", {"user_tags": ["kept"], "team": [99]}, format="json")
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "2"
        resp = SkillPackageViewSet.as_view({"patch": "partial_update"})(request, pk=pkg.id)
        assert resp.status_code == 200
        owner = _user(username="pkg_edit_owner", team_id=1)
        items = _listed_packages(owner, 1)
        matched = [item for item in items if item["package_id"] == "shared-edit"]
        assert len(matched) == 1
        assert matched[0]["user_tags"] == ["kept"]

    def test_other_group_delete_removes_row_and_storage(self, allow_team_instances, tmp_path, mocker):
        storage = tmp_path / "shared-delete" / "0.1.0"
        storage.mkdir(parents=True)
        (storage / "SKILL.md").write_text("# gone", encoding="utf-8")
        mocker.patch("apps.opspilot.viewsets.llm_view.DEFAULT_SKILL_PACKAGE_ROOT", tmp_path)
        pkg = SkillPackage.objects.create(
            package_id="shared-delete",
            name="Shared Delete",
            version="0.1.0",
            description="doomed",
            domain="domain.com",
            team=[1],
            storage_path=str(storage),
            is_build_in=False,
            is_enabled=True,
        )
        user = _user(username="pkg_delete", team_id=2)
        factory = APIRequestFactory()
        request = factory.delete("/")
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "2"
        resp = SkillPackageViewSet.as_view({"delete": "destroy"})(request, pk=pkg.id)
        assert resp.status_code == 204
        assert not SkillPackage.objects.filter(id=pkg.id).exists()
        assert not storage.exists()
        owner = _user(username="pkg_delete_owner", team_id=1)
        package_ids = {item["package_id"] for item in _listed_packages(owner, 1)}
        assert "shared-delete" not in package_ids

    def test_reimport_same_version_updates_saved_row(self, allow_team_instances, tmp_path, mocker):
        mocker.patch(
            "apps.opspilot.viewsets.llm_view.SkillPackageImporter",
            lambda: SkillPackageImporter(storage_root=tmp_path),
        )
        importer = _user(username="pkg_import", team_id=1)

        def _import(description, version):
            upload = SimpleUploadedFile("skill.zip", _skill_zip("shared-skill", version, description).getvalue(), content_type="application/zip")
            factory = APIRequestFactory()
            request = factory.post("/", {"file": upload}, format="multipart")
            force_authenticate(request, user=importer)
            request.COOKIES["current_team"] = "1"
            resp = SkillPackageViewSet.as_view({"post": "import_zip"})(request)
            assert resp.status_code == 200, _body(resp)
            return _body(resp)["data"]["id"]

        first_id = _import("first description", "1.0.0")
        second_id = _import("second description", "1.0.0")
        assert second_id == first_id
        reader = _user(username="pkg_import_reader", team_id=2)
        for viewer, team_id in ((importer, 1), (reader, 2)):
            matched = [item for item in _listed_packages(viewer, team_id) if item["id"] == first_id]
            assert len(matched) == 1
            assert matched[0]["description"] == "second description"

        other_id = _import("next description", "2.0.0")
        assert other_id != first_id
        still_old = [item for item in _listed_packages(reader, 2) if item["id"] == first_id]
        assert len(still_old) == 1
        assert still_old[0]["description"] == "second description"
        created = [item for item in _listed_packages(reader, 2) if item["id"] == other_id]
        assert len(created) == 1
        assert created[0]["description"] == "next description"

    def test_package_list_omits_agent_password(self, allow_team_instances):
        SkillPackage.objects.create(
            package_id="param-pack",
            name="Param Pack",
            version="0.1.0",
            description="params",
            domain="domain.com",
            team=[1],
            is_enabled=True,
        )
        LLMSkill.objects.create(
            name="agent-with-secret",
            domain="domain.com",
            team=[1],
            skill_package_params={"param-pack": [{"key": "pw", "type": "password", "value": "SENTINEL-PACKAGE-SECRET"}]},
        )
        user = _user(username="pkg_secret")
        rendered = json.dumps(_listed_packages(user, 1), ensure_ascii=False)
        assert "SENTINEL-PACKAGE-SECRET" not in rendered

    def test_other_group_lists_builtin_tools_and_hides_mcp(self, mocker):
        mocker.patch(
            "apps.core.utils.viewset_utils.get_permission_rules",
            return_value={"instance": [], "team": [2]},
        )
        SkillTools.objects.create(
            name="group-one-mcp",
            description="mcp",
            team=[1],
            is_build_in=False,
            params={"url": "http://mcp.example", "auth_token": "SENTINEL-MCP-TOKEN"},
        )
        SkillTools.objects.create(
            name="group-one-builtin",
            description="builtin",
            team=[1],
            is_build_in=True,
        )
        user = _user(username="pkg_tools", team_id=2)
        factory = APIRequestFactory()
        request = factory.get("/")
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "2"
        resp = SkillToolsViewSet.as_view({"get": "list"})(request)
        assert resp.status_code == 200
        payload = _body(resp)
        items = payload if isinstance(payload, list) else payload.get("items") or payload.get("results") or []
        rendered = json.dumps(items, ensure_ascii=False)
        assert "group-one-mcp" not in rendered
        assert "SENTINEL-MCP-TOKEN" not in rendered
        assert "group-one-builtin" in rendered


def _listed_tools(user, team_id):
    factory = APIRequestFactory()
    request = factory.get("/")
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = str(team_id)
    resp = SkillToolsViewSet.as_view({"get": "list"})(request)
    assert resp.status_code == 200
    payload = _body(resp)
    return payload if isinstance(payload, list) else payload.get("items") or payload.get("results") or []


def _delete_tool(user, team_id, pk):
    factory = APIRequestFactory()
    request = factory.delete("/")
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = str(team_id)
    return SkillToolsViewSet.as_view({"delete": "destroy"})(request, pk=pk)


def _tool_names(user, team_id):
    return {item["name"] for item in _listed_tools(user, team_id)}


class TestBuiltinToolDeleteGuard:
    def test_other_group_delete_builtin_rejected(self, allow_team_instances):
        tool = SkillTools.objects.create(
            name="shared-builtin",
            description="builtin",
            team=[1],
            is_build_in=True,
        )
        attacker = _user(username="tool_del_other", team_id=2, locale="zh-Hans")
        resp = _delete_tool(attacker, 2, tool.id)
        assert resp.status_code == 400
        body = _body(resp)
        assert body.get("result") is False
        assert body.get("message") == "内置工具不可删除"
        assert SkillTools.objects.filter(id=tool.id).exists()
        assert "shared-builtin" in _tool_names(attacker, 2)
        owner = _user(username="tool_del_owner", team_id=1, locale="zh-Hans")
        assert "shared-builtin" in _tool_names(owner, 1)

    def test_same_group_delete_builtin_rejected(self, allow_team_instances):
        tool = SkillTools.objects.create(
            name="owned-builtin",
            description="builtin",
            team=[1],
            is_build_in=True,
        )
        user = _user(username="tool_del_same", team_id=1, locale="zh-Hans")
        resp = _delete_tool(user, 1, tool.id)
        assert resp.status_code == 400
        body = _body(resp)
        assert body.get("result") is False
        assert body.get("message") == "内置工具不可删除"
        assert SkillTools.objects.filter(id=tool.id).exists()
        assert "owned-builtin" in _tool_names(user, 1)

    def test_other_group_cannot_delete_mcp(self, allow_team_instances):
        tool = SkillTools.objects.create(
            name="group-one-mcp-kept",
            description="mcp",
            team=[1],
            is_build_in=False,
        )
        attacker = _user(username="mcp_del_other", team_id=2)
        resp = _delete_tool(attacker, 2, tool.id)
        assert resp.status_code != 204
        assert SkillTools.objects.filter(id=tool.id).exists()
        assert "group-one-mcp-kept" not in _tool_names(attacker, 2)
        owner = _user(username="mcp_del_owner", team_id=1)
        assert "group-one-mcp-kept" in _tool_names(owner, 1)

    def test_same_group_deletes_non_builtin_mcp(self, allow_team_instances):
        tool = SkillTools.objects.create(
            name="group-one-mcp-gone",
            description="mcp",
            team=[1],
            is_build_in=False,
        )
        user = _user(username="mcp_del_same", team_id=1)
        resp = _delete_tool(user, 1, tool.id)
        assert resp.status_code == 204
        assert not SkillTools.objects.filter(id=tool.id).exists()
        assert "group-one-mcp-gone" not in _tool_names(user, 1)
