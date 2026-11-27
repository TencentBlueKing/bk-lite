import pytest

from apps.job_mgmt.constants import DangerousLevel
from apps.job_mgmt.models import DangerousRule, Playbook, Script
from apps.system_mgmt.models import Group, GroupDataRule

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(params=[Script, Playbook], ids=["script", "playbook"])
def library(request):
    return request.param


@pytest.fixture
def teams():
    return [Group.objects.create(name=name).pk for name in ("source", "destination", "other")]


def endpoint(model, action):
    return f"/api/v1/job_mgmt/api/{model._meta.model_name}/{action}/"


def post(client, model, action, **data):
    return client.post(endpoint(model, action), data, format="json")


def test_filtered_snapshot_and_delta_with_last_organization(library, teams, api_client, authenticated_user, mocker):
    a, b, c = teams
    module = library._meta.model_name + "_library"
    authenticated_user.permission = {"job": {module + "-View", module + "-Edit"}}
    authenticated_user.group_list = [{"id": a}, {"id": b}]
    api_client.cookies["current_team"] = str(a)
    mocker.patch("apps.core.utils.viewset_utils.get_permission_rules", return_value={"team": [a], "instance": []})
    changed = library.objects.create(name="wanted", team=[a, b])
    blocked = library.objects.create(name="wanted too", team=[a])
    library.objects.create(name="wanted other", team=[c])
    library.objects.create(name="irrelevant", team=[a])
    snapshot = api_client.get(endpoint(library, "selection_ids"), {"name": "wanted", "page_size": 1})
    assert snapshot.status_code == 200
    assert set(snapshot.data["ids"]) == {changed.pk, blocked.pk}
    command = dict(ids=snapshot.data["ids"], operation="remove", organization=a)
    preview = post(api_client, library, "adjust_organizations", **command)
    assert preview.status_code == 200
    assert preview.data["blocked"] == [{"id": blocked.pk, "name": blocked.name}]
    assert preview.data["changed"] == 1
    command["preview_token"] = preview.data["preview_token"]
    assert post(api_client, library, "adjust_organizations", **command).status_code == 400
    rule = GroupDataRule.objects.create(
        name="shared job instance IDs", app="job", group_id=a, group_name="a", rules={"job": [{"id": str(changed.pk)}]}
    )
    applied = post(api_client, library, "adjust_organizations", **command, exclude_blocked=True)
    assert applied.status_code == 200
    changed.refresh_from_db()
    blocked.refresh_from_db()
    rule.refresh_from_db()
    assert changed.team == [b] and blocked.team == [a]
    assert rule.rules["job"] == [{"id": str(changed.pk)}]


def test_apply_rechecks_permissions_before_any_change(library, teams, api_client, authenticated_user, mocker):
    a, b, _ = teams
    module = library._meta.model_name + "_library"
    authenticated_user.permission = {"job": {module + "-Edit", module + "-Delete"}}
    authenticated_user.group_list = [{"id": a}, {"id": b}]
    api_client.cookies["current_team"] = str(a)
    rules = {"team": [a], "instance": []}
    mocker.patch("apps.core.utils.viewset_utils.get_permission_rules", return_value=rules)
    first = library.objects.create(name="first", team=[a])
    second = library.objects.create(name="second", team=[a])
    payload = dict(ids=[first.pk, second.pk], operation="add", organization=b)
    preview = post(api_client, library, "adjust_organizations", **payload)
    assert preview.status_code == 200
    rules.update(team=[], instance=[{"id": first.pk, "permission": ["Operate"]}])
    cleanup = mocker.patch.object(Playbook, "delete_storage_files")
    assert post(api_client, library, "adjust_organizations", **payload, preview_token=preview.data["preview_token"]).status_code == 403
    assert post(api_client, library, "batch_delete", ids=payload["ids"]).status_code == 403
    assert list(library.objects.order_by("pk").values_list("team", flat=True)) == [[a], [a]]
    cleanup.assert_not_called()


def test_token_cannot_cross_template_libraries_or_stale_teams(su_client, teams):
    a, b, c = teams
    script = Script.objects.create(name="overlapping id", team=[a])
    pb = Playbook.objects.create(pk=script.pk, name=script.name, team=[a])
    payload = dict(ids=[script.pk], operation="add", organization=b)
    preview = post(su_client, Script, "adjust_organizations", **payload)
    assert preview.status_code == 200
    token = preview.data["preview_token"]
    assert post(su_client, Playbook, "adjust_organizations", **payload, preview_token=token).status_code == 409
    Script.objects.filter(pk=script.pk).update(team=[a, c])
    assert post(su_client, Script, "adjust_organizations", **payload, preview_token=token).status_code == 409
    pb.refresh_from_db()
    assert pb.team == [a]


@pytest.mark.parametrize("conflict", ["existing", "selected", "dangerous"])
def test_script_batch_preserves_name_and_dangerous_rule_constraints(conflict, su_client, teams):
    a, b, c = teams
    first = Script.objects.create(name="same", team=[a], content="forbidden-content")
    ids = [first.pk]
    if conflict == "dangerous":
        DangerousRule.objects.create(name="forbidden", pattern="forbidden-content", level=DangerousLevel.FORBIDDEN, team=[b])
    else:
        second = Script.objects.create(name="same", team=[b if conflict == "existing" else c], content="echo ok")
        if conflict == "selected":
            ids.append(second.pk)
    response = post(su_client, Script, "adjust_organizations", ids=ids, operation="add", organization=b)
    assert response.status_code == 400
    first.refresh_from_db()
    assert first.team == [a]


def test_built_in_script_protects_whole_delete(su_client):
    script = Script.objects.create(name="builtin", is_built_in=True, team=[1])
    other = Script.objects.create(name="custom", team=[1])
    assert post(su_client, Script, "batch_delete", ids=[other.pk, script.pk]).status_code == 400
    assert su_client.delete(endpoint(Script, script.pk)).status_code == 400
    assert set(Script.objects.values_list("pk", flat=True)) == {script.pk, other.pk}


def test_export_only_visible_scripts(api_client, authenticated_user, mocker):
    authenticated_user.permission = {"job": {"script_library-View"}}
    api_client.cookies["current_team"] = "1"
    mocker.patch("apps.core.utils.viewset_utils.get_permission_rules", return_value={"team": [1], "instance": []})
    visible = Script.objects.create(name="mine", team=[1])
    hidden = Script.objects.create(name="theirs", team=[2])
    assert post(api_client, Script, "export", ids=[visible.pk, hidden.pk]).status_code == 400


def test_add_and_repeat_leave_other_organizations_and_revision_data_intact(library, teams, su_client):
    a, b, c = teams
    item = library.objects.create(name="existing", team=[a, c])
    already = library.objects.create(name="already assigned", team=[a, b])
    payload = dict(operation="add", organization=b, ids=[item.pk, already.pk, item.pk])
    preview = post(su_client, library, "adjust_organizations", **payload)
    assert preview.status_code == 200
    assert (preview.data["changed"], preview.data["unchanged"]) == (1, 1)
    confirmed = post(su_client, library, "adjust_organizations", **payload, preview_token=preview.data["preview_token"])
    assert confirmed.status_code == 200
    item.refresh_from_db()
    assert item.team == [a, c, b] and item.revisions.count() == 0
    assert post(su_client, library, "adjust_organizations", **payload, preview_token=preview.data["preview_token"]).status_code == 409
    again = post(su_client, library, "adjust_organizations", **payload)
    assert (again.data["changed"], again.data["unchanged"]) == (0, 2)


def test_new_script_name_conflict_between_preview_and_apply(su_client, teams):
    a, b, _ = teams
    script = Script.objects.create(name="nightly", team=[a], content="echo ok")
    payload = dict(ids=[script.pk], operation="add", organization=b)
    preview = post(su_client, Script, "adjust_organizations", **payload)
    assert preview.status_code == 200
    Script.objects.create(name=script.name, team=[b])
    assert post(su_client, Script, "adjust_organizations", **payload, preview_token=preview.data["preview_token"]).status_code == 400
    script.refresh_from_db()
    assert script.team == [a]
