"""高危规则 / 高危路径视图集成测试（覆盖 dangerous_base / dangerous_path / dangerous_rule）"""

import pytest

from apps.job_mgmt.constants import DangerousLevel, MatchType
from apps.job_mgmt.models import DangerousPath, DangerousRule

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

RULE_URL = "/api/v1/job_mgmt/api/dangerous_rule/"
PATH_URL = "/api/v1/job_mgmt/api/dangerous_path/"


class TestDangerousRuleViewSet:
    def test_create_returns_201_and_persists(self, su_client):
        resp = su_client.post(
            RULE_URL,
            {"name": "禁止 rm", "pattern": "rm -rf", "level": DangerousLevel.FORBIDDEN, "team": [1]},
            format="json",
        )
        assert resp.status_code == 201
        assert DangerousRule.objects.filter(name="禁止 rm").exists()

    def test_list_returns_rules(self, su_client):
        DangerousRule.objects.create(name="r1", pattern="rm", level=DangerousLevel.CONFIRM, team=[1])
        resp = su_client.get(RULE_URL)
        assert resp.status_code == 200

    def test_retrieve_returns_rule(self, su_client):
        rule = DangerousRule.objects.create(name="r1", pattern="rm", level=DangerousLevel.CONFIRM, team=[1])
        resp = su_client.get(f"{RULE_URL}{rule.id}/")
        assert resp.status_code == 200
        assert resp.data["name"] == "r1"

    def test_update_changes_fields(self, su_client):
        rule = DangerousRule.objects.create(name="r1", pattern="rm", level=DangerousLevel.CONFIRM, team=[1])
        resp = su_client.put(
            f"{RULE_URL}{rule.id}/",
            {"name": "r1-edit", "pattern": "rm -rf", "level": DangerousLevel.FORBIDDEN, "team": [1]},
            format="json",
        )
        assert resp.status_code == 200
        rule.refresh_from_db()
        assert rule.name == "r1-edit"

    def test_destroy_removes_rule(self, su_client):
        rule = DangerousRule.objects.create(name="r1", pattern="rm", level=DangerousLevel.CONFIRM, team=[1])
        resp = su_client.delete(f"{RULE_URL}{rule.id}/")
        assert resp.status_code in (200, 204)
        assert not DangerousRule.objects.filter(id=rule.id).exists()

    def test_enabled_rules_groups_by_level(self, su_client):
        DangerousRule.objects.create(name="c", pattern="ls", level=DangerousLevel.CONFIRM, is_enabled=True, team=[1])
        DangerousRule.objects.create(name="f", pattern="rm", level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[1])
        DangerousRule.objects.create(name="off", pattern="dd", level=DangerousLevel.FORBIDDEN, is_enabled=False, team=[1])
        resp = su_client.get(f"{RULE_URL}enabled_rules/")
        assert resp.status_code == 200
        assert "ls" in resp.data[DangerousLevel.CONFIRM]
        assert "rm" in resp.data[DangerousLevel.FORBIDDEN]
        assert "dd" not in resp.data[DangerousLevel.FORBIDDEN]

    def test_builtin_is_visible_and_superuser_can_edit_and_delete(self, su_client):
        rule = DangerousRule.objects.create(
            name="系统规则", pattern="shutdown", level=DangerousLevel.CONFIRM,
            is_builtin=True, team=[],
        )

        list_resp = su_client.get(f"{RULE_URL}?page_size=100")
        assert list_resp.status_code == 200
        listed_rule = next(item for item in list_resp.data["items"] if item["id"] == rule.id)
        assert listed_rule["is_builtin"] is True
        assert set(listed_rule).isdisjoint({"preset_key", "preset_version", "disabled_reason", "disabled_by", "disabled_at", "can_toggle"})

        edit_resp = su_client.patch(f"{RULE_URL}{rule.id}/", {"name": "被修改"}, format="json")
        assert edit_resp.status_code == 200
        rule.refresh_from_db()
        assert rule.name == "被修改"

        delete_resp = su_client.delete(f"{RULE_URL}{rule.id}/")
        assert delete_resp.status_code in (200, 204)
        assert not DangerousRule.objects.filter(id=rule.id).exists()

    def test_builtin_toggle_does_not_require_reason(self, su_client):
        rule = DangerousRule.objects.create(
            name="系统规则", pattern="shutdown", level=DangerousLevel.CONFIRM,
            is_builtin=True, team=[],
        )

        resp = su_client.patch(f"{RULE_URL}{rule.id}/", {"is_enabled": False}, format="json")
        assert resp.status_code == 200
        rule.refresh_from_db()
        assert rule.is_enabled is False

    def test_non_superuser_cannot_operate_builtin(self, api_client, authenticated_user):
        authenticated_user.is_superuser = False
        authenticated_user.permission = {
            "job": {"dangerous_command-View", "dangerous_command-Edit", "dangerous_command-Delete"},
        }
        api_client.cookies["current_team"] = "1"
        rule = DangerousRule.objects.create(
            name="系统规则", pattern="shutdown", level=DangerousLevel.CONFIRM,
            is_builtin=True, team=[],
        )

        edit_resp = api_client.patch(f"{RULE_URL}{rule.id}/", {"name": "被修改"}, format="json")
        delete_resp = api_client.delete(f"{RULE_URL}{rule.id}/")

        assert edit_resp.status_code == 403
        assert delete_resp.status_code == 403
        assert DangerousRule.objects.filter(id=rule.id, name="系统规则").exists()

    def test_enabled_rules_includes_global_builtin(self, su_client):
        DangerousRule.objects.create(
            name="全局规则", pattern="global-danger", level=DangerousLevel.FORBIDDEN,
            is_builtin=True, is_enabled=True, team=[],
        )
        resp = su_client.get(f"{RULE_URL}enabled_rules/")
        assert resp.status_code == 200
        assert "global-danger" in resp.data[DangerousLevel.FORBIDDEN]


class TestDangerousPathViewSet:
    def test_create_returns_201(self, su_client):
        resp = su_client.post(
            PATH_URL,
            {"name": "保护 /etc", "pattern": "/etc", "match_type": MatchType.EXACT, "level": DangerousLevel.FORBIDDEN, "team": [1]},
            format="json",
        )
        assert resp.status_code == 201
        assert DangerousPath.objects.filter(pattern="/etc").exists()

    def test_list_returns_paths(self, su_client):
        DangerousPath.objects.create(name="p1", pattern="/etc", match_type=MatchType.EXACT, team=[1])
        resp = su_client.get(PATH_URL)
        assert resp.status_code == 200

    def test_retrieve_returns_path(self, su_client):
        p = DangerousPath.objects.create(name="p1", pattern="/etc", match_type=MatchType.EXACT, team=[1])
        resp = su_client.get(f"{PATH_URL}{p.id}/")
        assert resp.status_code == 200
        assert resp.data["pattern"] == "/etc"

    def test_update_changes_pattern(self, su_client):
        p = DangerousPath.objects.create(name="p1", pattern="/etc", match_type=MatchType.EXACT, team=[1])
        resp = su_client.patch(f"{PATH_URL}{p.id}/", {"pattern": "/var"}, format="json")
        assert resp.status_code == 200
        p.refresh_from_db()
        assert p.pattern == "/var"

    def test_destroy_removes_path(self, su_client):
        p = DangerousPath.objects.create(name="p1", pattern="/etc", match_type=MatchType.EXACT, team=[1])
        resp = su_client.delete(f"{PATH_URL}{p.id}/")
        assert resp.status_code in (200, 204)
        assert not DangerousPath.objects.filter(id=p.id).exists()

    def test_enabled_paths_groups_by_level_and_match_type(self, su_client):
        DangerousPath.objects.create(name="e", pattern="/etc", match_type=MatchType.EXACT, level=DangerousLevel.FORBIDDEN, is_enabled=True, team=[1])
        DangerousPath.objects.create(name="r", pattern="/var/.*", match_type=MatchType.REGEX, level=DangerousLevel.CONFIRM, is_enabled=True, team=[1])
        resp = su_client.get(f"{PATH_URL}enabled_paths/")
        assert resp.status_code == 200
        assert "/etc" in resp.data[DangerousLevel.FORBIDDEN][MatchType.EXACT]
        assert "/var/.*" in resp.data[DangerousLevel.CONFIRM][MatchType.REGEX]

    def test_enabled_paths_includes_global_builtin(self, su_client):
        DangerousPath.objects.create(
            name="全局路径", pattern="/global-danger", match_type=MatchType.EXACT,
            level=DangerousLevel.FORBIDDEN, is_builtin=True,
            is_enabled=True, team=[],
        )
        resp = su_client.get(f"{PATH_URL}enabled_paths/")
        assert resp.status_code == 200
        assert "/global-danger" in resp.data[DangerousLevel.FORBIDDEN][MatchType.EXACT]

    def test_non_superuser_cannot_operate_builtin(self, api_client, authenticated_user):
        authenticated_user.is_superuser = False
        authenticated_user.permission = {
            "job": {"dangerous_path-View", "dangerous_path-Edit", "dangerous_path-Delete"},
        }
        api_client.cookies["current_team"] = "1"
        path = DangerousPath.objects.create(
            name="系统路径", pattern="/etc", match_type=MatchType.EXACT,
            is_builtin=True, team=[],
        )

        edit_resp = api_client.patch(f"{PATH_URL}{path.id}/", {"pattern": "/tmp"}, format="json")
        delete_resp = api_client.delete(f"{PATH_URL}{path.id}/")

        assert edit_resp.status_code == 403
        assert delete_resp.status_code == 403
        assert DangerousPath.objects.filter(id=path.id, pattern="/etc").exists()
