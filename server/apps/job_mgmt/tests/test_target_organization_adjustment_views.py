"""Job 目标批量调整组织：选择范围、预览确认和权限边界。"""

import pytest

from apps.core.utils.permission_cache import get_user_permission_version
from apps.job_mgmt.models import Target, TargetTeamMembership
from apps.system_mgmt.models import Group, GroupDataRule, UserRule

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

BASE_URL = "/api/v1/job_mgmt/api/target/"
ADJUST_URL = BASE_URL + "adjust_organizations/"
SELECTION_URL = BASE_URL + "selection_ids/"


@pytest.fixture
def teams():
    return tuple(Group.objects.create(name=f"job-batch-{name}").pk for name in ("A", "B", "C", "D"))


@pytest.fixture
def editor(api_client, authenticated_user, teams, mocker):
    a, b, *_ = teams
    authenticated_user.group_list = [{"id": a}, {"id": b}]
    authenticated_user.permission = {"job": {"target-Edit", "target-View"}}
    api_client.cookies["current_team"] = str(a)
    rules = {"team": [a], "instance": []}
    mocker.patch("apps.rpc.system_mgmt.SystemMgmt.get_user_rules_by_app", return_value=rules)
    return api_client, rules


def make_target(name, team):
    return Target.objects.create(name=name, ip="192.0.2.1", team=team)


def check_team(target, expected):
    target.refresh_from_db()
    assert sorted(target.team) == sorted(expected)
    assert set(TargetTeamMembership.objects.filter(target=target).values_list("team_id", flat=True)) == set(expected)


def post(client, payload, **extra):
    return client.post(ADJUST_URL, {**payload, **extra}, format="json")


def preview_token(client, payload):
    response = post(client, payload)
    assert response.status_code == 200, response.content
    return response.data["preview_token"]


def test_remove_requires_explicit_exclusion_and_preserves_other_memberships(su_client, teams):
    a, b, c, d = teams
    shared = make_target("shared", [b, c])
    second_shared = make_target("also shared", [b, c])
    independent = make_target("independent", [d])
    blocked = make_target("only B", [b])
    outside = make_target("outside the selection", [a, b])
    payload = {"ids": [shared.pk, second_shared.pk, independent.pk, blocked.pk], "operation": "remove", "organization": b}

    preview = post(su_client, payload)
    assert preview.status_code == 200, preview.content
    assert (preview.data["changed"], preview.data["unchanged"]) == (2, 1)
    assert preview.data["blocked"] == [{"id": blocked.pk, "name": blocked.name}]
    assert {"before": [b, c], "after": [c], "count": 2} in preview.data["groups"]
    token = preview.data["preview_token"]
    check_team(shared, [b, c])

    rejected = post(su_client, payload, preview_token=token)
    assert rejected.status_code in (400, 409)
    check_team(shared, [b, c])
    result = post(su_client, payload, preview_token=token, exclude_blocked=True)
    assert result.status_code == 200, result.content
    check_team(shared, [c])
    check_team(second_shared, [c])
    check_team(independent, [d])
    check_team(blocked, [b])
    check_team(outside, [a, b])


def test_add_preserves_legacy_team_memberships_and_is_repeatable(su_client, teams):
    a, b, c, _ = teams
    legacy = make_target("legacy", [str(b), {"id": c}])
    already = make_target("already", [a, c])
    payload = {"ids": [legacy.pk, already.pk], "operation": "add", "organization": a}
    token = preview_token(su_client, payload)
    result = post(su_client, payload, preview_token=token)
    assert result.status_code == 200, result.content
    legacy.refresh_from_db()
    assert legacy.team == [str(b), {"id": c}, a]
    assert set(TargetTeamMembership.objects.filter(target=legacy).values_list("team_id", flat=True)) == {a, b, c}
    check_team(already, [a, c])
    second = post(su_client, payload)
    assert second.status_code == 200
    assert (second.data["changed"], second.data["unchanged"]) == (0, 2)


def test_newer_membership_on_one_target_invalidates_entire_preview(su_client, teams):
    a, b, c, d = teams
    first = make_target("first", [a])
    second = make_target("second", [c])
    payload = {"ids": [first.pk, second.pk], "operation": "add", "organization": b}
    token = preview_token(su_client, payload)
    Target.objects.filter(pk=second.pk).update(team=[c, d])
    stale = post(su_client, payload, preview_token=token)
    assert stale.status_code == 409
    check_team(first, [a])
    check_team(second, [c, d])


def test_selection_respects_name_page_independence_and_tenant_scope(editor, teams):
    client, _ = editor
    a, b, *_ = teams
    first = make_target("prod-app", [a, b])
    second = make_target("prod-db", [a])
    make_target("test-app", [a])
    make_target("prod-foreign", [b])
    response = client.get(SELECTION_URL, {"name": "prod", "page_size": 1})
    assert response.status_code == 200, response.content
    assert set(response.data["ids"]) == {first.pk, second.pk}
    visible = client.get(BASE_URL, {"name": "prod", "page_size": 20})
    assert visible.status_code == 200
    assert response.data["ids"] == [item["id"] for item in visible.data["items"]]


def test_mixed_selection_cannot_preview_foreign_target(editor, teams):
    client, _ = editor
    a, b, *_ = teams
    own = make_target("own", [a])
    foreign = make_target("private-target", [b])
    payload = {"ids": [own.pk, foreign.pk], "operation": "add", "organization": b}
    response = post(client, payload)
    assert response.status_code == 403
    assert foreign.name.encode() not in response.content
    check_team(own, [a])
    check_team(foreign, [b])


def test_revoked_instance_operate_permission_prevents_commit(editor, teams):
    client, rules = editor
    a, b, *_ = teams
    target = make_target("scoped", [a])
    rules.update(team=[], instance=[{"id": target.pk, "permission": ["View", "Operate"]}])
    payload = {"ids": [target.pk], "operation": "add", "organization": b}
    token = preview_token(client, payload)
    rules["instance"][0]["permission"] = ["View"]
    response = post(client, payload, preview_token=token)
    assert response.status_code == 403
    check_team(target, [a])


def test_destination_organization_must_be_assignable_and_active(editor, teams):
    client, _ = editor
    a, b, c, _ = teams
    target = make_target("movable", [a])
    payload = {"ids": [target.pk], "operation": "add", "organization": c}
    assert post(client, payload).status_code == 403
    Group.objects.filter(pk=b).update(is_delete=True)
    assert post(client, payload, organization=b).status_code in (400, 403, 404)
    check_team(target, [a])


def test_view_only_actor_cannot_adjust(api_client, authenticated_user, teams):
    a, b, *_ = teams
    authenticated_user.group_list = [{"id": a}, {"id": b}]
    authenticated_user.permission = {"job": {"target-View"}}
    api_client.cookies["current_team"] = str(a)
    target = make_target("viewable", [a])
    response = post(api_client, {"ids": [target.pk], "operation": "add", "organization": b})
    assert response.status_code == 403
    check_team(target, [a])


def test_large_selection_is_rejected_without_returning_a_truncated_snapshot(editor, teams):
    client, _ = editor
    a, b, *_ = teams
    targets = Target.objects.bulk_create([Target(name=f"bulk-{i}", ip="192.0.2.2", team=[a]) for i in range(1001)])
    assert client.get(SELECTION_URL, {"name": "bulk-"}).status_code == 400
    response = post(client, {"ids": [r.pk for r in targets], "operation": "add", "organization": b})
    assert response.status_code == 400
    assert not TargetTeamMembership.objects.filter(team_id=b).exists()


@pytest.mark.parametrize("version_write_fails", [False, True], ids=["commit", "rollback"])
def test_removal_and_instance_grant_revocation_commit_together(su_client, teams, mocker, version_write_fails):
    a, b, *_ = teams
    target = make_target("shared", [a, b])
    rule = GroupDataRule.objects.create(name="target grants", group_id=b, group_name="B", app="job", rules={"job": [{"id": str(target.pk)}]})
    UserRule.objects.create(username="operator", domain="domain.com", group_rule=rule)
    version = get_user_permission_version("operator", "domain.com")
    payload = {"ids": [target.pk], "operation": "remove", "organization": b}
    token = preview_token(su_client, payload)
    if version_write_fails:
        mocker.patch("apps.core.utils.permission_cache._advance_user_permission_versions", side_effect=RuntimeError("forced write failure"))
        su_client.raise_request_exception = False

    response = post(su_client, payload, preview_token=token)
    rule.refresh_from_db()
    if version_write_fails:
        assert response.status_code >= 500
        check_team(target, [a, b])
        assert rule.rules["job"] == [{"id": str(target.pk)}]
        assert get_user_permission_version("operator", "domain.com") == version
    else:
        assert response.status_code == 200
        check_team(target, [a])
        assert {str(item["id"]) for item in rule.rules["job"]} == {"-1"}
        assert get_user_permission_version("operator", "domain.com") > version


def test_confirmed_snapshot_cannot_be_reused_for_other_ids_or_destination(su_client, teams):
    a, b, c, _ = teams
    first = make_target("previewed", [a])
    second = make_target("not previewed", [a])
    payload = {"ids": [first.pk], "operation": "add", "organization": b}
    token = preview_token(su_client, payload)
    for changed_request in ({"ids": [second.pk]}, {"organization": c}, {"operation": "remove"}):
        response = post(su_client, payload, preview_token=token, **changed_request)
        assert response.status_code in (400, 409)
    check_team(first, [a])
    check_team(second, [a])


def test_other_membership_grant_does_not_confer_operate_in_current_team(editor, teams):
    client, rules = editor
    a, b, *_ = teams
    rules.update(team=[b], instance=[])
    target = make_target("two memberships", [a, b])
    response = post(client, {"ids": [target.pk], "operation": "remove", "organization": b})
    assert response.status_code == 403
    check_team(target, [a, b])


def test_malformed_rule_response_never_authorizes_preview(editor, teams, mocker):
    client, _ = editor
    a, b, *_ = teams
    target = make_target("restricted", [a])
    mocker.patch("apps.rpc.system_mgmt.SystemMgmt.get_user_rules_by_app", return_value=["bad rule"])
    response = post(client, {"ids": [target.pk], "operation": "add", "organization": b})
    assert response.status_code == 403
    check_team(target, [a])
