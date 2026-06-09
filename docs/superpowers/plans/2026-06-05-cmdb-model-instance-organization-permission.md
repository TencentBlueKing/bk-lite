# CMDB Model / Instance Organization-Scoped Permission Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix CMDB object-level permission checks so model / instance name matches only grant access when the matched permission comes from one of the current object's organizations.

**Architecture:** Keep the current `permission_instances_map` contract and the existing view call graph unchanged. Make the final permission consumers organization-aware: `CmdbRulesFormatUtil.has_object_permission()` decides access by intersecting object organizations with the matched permission record’s `organization` set, and the two permission backfill helpers only merge permissions that come from the current object’s own organizations.

**Tech Stack:** Python 3.12, Django/DRF, existing CMDB helper/view tests under `server/apps/cmdb/tests`, pytest via `uv run pytest`.

---

## File Structure

- Modify: `server/apps/cmdb/utils/permission_util.py:94-141` — tighten final object permission checks for `obj_type == "model"` and `obj_type == "instances"` so name-scoped permission records only apply when their `organization` set overlaps the current object’s organizations.
- Modify: `server/apps/cmdb/utils/permission_util.py:245-271` — keep the aggregate index shape unchanged, but treat the stored `organization` set as a required part of later permission evaluation.
- Modify: `server/apps/cmdb/views/instance.py:149-181` — only backfill instance permissions from matching organizations instead of blindly consuming a same-name aggregate entry.
- Modify: `server/apps/cmdb/views/model.py:32-54` — only backfill model permissions from the current model’s `group` membership instead of blindly consuming a same-`model_id` aggregate entry.
- Modify: `server/apps/cmdb/tests/test_permission_util.py:127-159` — add helper-level regressions for same-name cross-organization deny and same-organization allow paths.
- Modify: `server/apps/cmdb/tests/test_misc_views.py:85-154` — add mixin-level regressions proving view-facing permission helpers do not accept cross-organization name matches.
- Modify: `server/apps/cmdb/tests/test_instance_views.py:153-170,206-265` — add pure-function and representative retrieve-path regressions for cross-organization instance permission leakage.
- Modify: `server/apps/cmdb/tests/test_model_views.py:69-79,87-170` — add pure-function and representative model detail / delete regressions for cross-organization model permission leakage.

## Task 1: Lock helper and mixin permission behavior

**Files:**
- Modify: `server/apps/cmdb/utils/permission_util.py:94-141`
- Modify: `server/apps/cmdb/tests/test_permission_util.py:150-159`
- Modify: `server/apps/cmdb/tests/test_misc_views.py:85-154`

- [ ] **Step 1: Write the failing helper and mixin tests**

```python
# server/apps/cmdb/tests/test_permission_util.py
def test_has_object_permission_instances_same_name_other_org_denied():
    pmap = {6: {"permission_instances_map": {"prod-vc": ["View"]}}}
    instance = {"inst_name": "prod-vc", "organization": [9]}
    assert U.has_object_permission("instances", VIEW, "vmware_vc", pmap, instance) is False


def test_has_object_permission_model_same_model_id_other_org_denied():
    pmap = {6: {"permission_instances_map": {"vmware_vc": ["Operate"]}}}
    model = {"model_id": "vmware_vc", "group": [9]}
    assert U.has_object_permission("model", OPERATE, "vmware_vc", pmap, model, default_group_id=1) is False


def test_has_object_permission_model_same_org_allowed():
    pmap = {6: {"permission_instances_map": {"vmware_vc": ["Operate"]}}}
    model = {"model_id": "vmware_vc", "group": [6]}
    assert U.has_object_permission("model", OPERATE, "vmware_vc", pmap, model, default_group_id=1) is True
```

```python
# server/apps/cmdb/tests/test_misc_views.py
def test_check_instance_permission_same_name_other_org_denied(monkeypatch):
    mixin = CmdbPermissionMixin()
    monkeypatch.setattr(
        "apps.cmdb.views.mixins.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda **k: {6: {"permission_instances_map": {"prod-vc": ["View"]}}},
    )
    req = _mixin_request([{"id": 9}], current_team="9")
    instance = {"organization": [9], "inst_name": "prod-vc", "model_id": "vmware_vc"}
    assert mixin.check_instance_permission(req, instance) is False


def test_check_model_permission_same_model_id_other_org_denied(monkeypatch):
    mixin = CmdbPermissionMixin()
    monkeypatch.setattr(
        "apps.cmdb.views.mixins.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda **k: {6: {"permission_instances_map": {"vmware_vc": ["Operate"]}}},
    )
    req = _mixin_request([{"id": 9}])
    model = {"group": [9], "model_id": "vmware_vc"}
    assert mixin.check_model_permission(req, model, operator=OPERATE) is False
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `cd server && uv run pytest apps/cmdb/tests/test_permission_util.py apps/cmdb/tests/test_misc_views.py -k "same_name_other_org or same_model_id_other_org or same_org_allowed" -v`

Expected: FAIL because `has_object_permission()` currently allows a same-name / same-`model_id` match even when the matched permission came from a different organization.

- [ ] **Step 3: Implement the minimal helper fix**

```python
# server/apps/cmdb/utils/permission_util.py
@staticmethod
def _organizations_intersect(obj_organizations, permission_data):
    return bool(set(obj_organizations or []) & set(permission_data.get("organization", set())))


@staticmethod
def has_object_permission(obj_type, operator, model_id, permission_instances_map, instance, team_id=None,
                          default_group_id=None):
    organizations_instances_map = CmdbRulesFormatUtil.format_organizations_instances_map(permission_instances_map)

    if obj_type == "model":
        groups = instance.get("group", [])
        if default_group_id in groups and operator == VIEW:
            return True

        for group in groups:
            if group in organizations_instances_map and operator in organizations_instances_map[group]["permission"]:
                return True

        model_permission = organizations_instances_map.get(model_id)
        if model_permission and operator in model_permission["permission"]:
            return CmdbRulesFormatUtil._organizations_intersect(groups, model_permission)

        return False

    if obj_type == "instances":
        organizations = instance.get("organization", [])
        for organization in organizations:
            if organization in organizations_instances_map and operator in organizations_instances_map[organization]["permission"]:
                return True

        inst_permission = organizations_instances_map.get(instance.get("inst_name"))
        if inst_permission and operator in inst_permission["permission"]:
            return CmdbRulesFormatUtil._organizations_intersect(organizations, inst_permission)

    return False
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `cd server && uv run pytest apps/cmdb/tests/test_permission_util.py apps/cmdb/tests/test_misc_views.py -k "same_name_other_org or same_model_id_other_org or same_org_allowed" -v`

Expected: PASS with helper-level deny/allow behavior matching organization intersections.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/utils/permission_util.py \
        server/apps/cmdb/tests/test_permission_util.py \
        server/apps/cmdb/tests/test_misc_views.py
git commit -m "fix: scope cmdb object permissions by organization"
```

## Task 2: Fix instance permission backfill and instance view regression

**Files:**
- Modify: `server/apps/cmdb/views/instance.py:149-181`
- Modify: `server/apps/cmdb/tests/test_instance_views.py:153-170,211-265`

- [ ] **Step 1: Write the failing instance tests**

```python
# server/apps/cmdb/tests/test_instance_views.py
def test_add_instance_permission_same_name_other_org_denied():
    instances = [{"_creator": "bob", "inst_name": "prod-vc", "organization": [9]}]
    pmap = {6: {"permission_instances_map": {"prod-vc": ["View"]}}}
    InstanceViewSet.add_instance_permission(instances, pmap, creator="alice")
    assert instances[0]["permission"] == []


def test_add_instance_permission_same_name_same_org_allowed():
    instances = [{"_creator": "bob", "inst_name": "prod-vc", "organization": [6]}]
    pmap = {6: {"permission_instances_map": {"prod-vc": ["View"]}}}
    InstanceViewSet.add_instance_permission(instances, pmap, creator="alice")
    assert instances[0]["permission"] == ["View"]


@pytest.mark.django_db
def test_retrieve_denied_when_name_permission_only_exists_in_other_org(superuser, monkeypatch):
    from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil as PermissionUtil

    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 5, "model_id": "vmware_vc", "inst_name": "prod-vc", "organization": [9], "_creator": "alice"},
    )
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.check_creator_and_organizations", lambda self, r, i: False)
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.organizations", lambda self, r, i: [9])
    monkeypatch.setattr(f"{VIEWS}.CmdbRulesFormatUtil.has_object_permission", PermissionUtil.has_object_permission)
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda request, model_id="", permission_type=None: {
            6: {"permission_instances_map": {"prod-vc": ["View"]}, "inst_names": ["prod-vc"]}
        },
    )
    response = _call({"get": "retrieve"}, _req("get", superuser, team="9"), pk="5")
    assert response.status_code == status.HTTP_403_FORBIDDEN
```

- [ ] **Step 2: Run the focused instance tests to verify they fail**

Run: `cd server && uv run pytest apps/cmdb/tests/test_instance_views.py -k "same_name_other_org or same_name_same_org_allowed or other_org" -v`

Expected: FAIL because `add_instance_permission()` currently backfills `permission` from any same-name aggregate entry, and the retrieve path still trusts that helper chain.

- [ ] **Step 3: Implement the minimal instance backfill fix**

```python
# server/apps/cmdb/views/instance.py
organizations_instances_map = CmdbRulesFormatUtil.format_organizations_instances_map(permission_instances_map)
for instance in instances:
    _creator = instance.get("_creator")
    if _creator == creator:
        instance["permission"] = [VIEW, OPERATE]
        continue

    instance["permission"] = []
    organizations = instance["organization"]

    for organization in organizations:
        if organization not in organizations_instances_map:
            continue
        for _permission in organizations_instances_map[organization]["permission"]:
            if _permission not in instance["permission"]:
                instance["permission"].append(_permission)

    inst_permission = organizations_instances_map.get(instance["inst_name"])
    if inst_permission and set(organizations) & set(inst_permission["organization"]):
        for _permission in inst_permission["permission"]:
            if _permission not in instance["permission"]:
                instance["permission"].append(_permission)
```

- [ ] **Step 4: Run the focused instance tests to verify they pass**

Run: `cd server && uv run pytest apps/cmdb/tests/test_instance_views.py -k "same_name_other_org or same_name_same_org_allowed or other_org" -v`

Expected: PASS with same-name instance permissions only backfilled from matching organizations, and representative retrieve denial enforced.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/views/instance.py \
        server/apps/cmdb/tests/test_instance_views.py
git commit -m "fix: restrict cmdb instance permission backfill"
```

## Task 3: Fix model permission backfill and model view regression

**Files:**
- Modify: `server/apps/cmdb/views/model.py:32-54`
- Modify: `server/apps/cmdb/tests/test_model_views.py:69-79,95-170`

- [ ] **Step 1: Write the failing model tests**

```python
# server/apps/cmdb/tests/test_model_views.py
def test_model_add_permission_same_model_id_other_org_denied():
    models = [{"model_id": "host", "group": [9]}]
    pmap = {6: {"permission_instances_map": {"host": ["View"]}}}
    ModelViewSet.model_add_permission(models, permission_instances_map=pmap, default_group=1)
    assert models[0]["permission"] == []


def test_model_add_permission_same_model_id_same_org_allowed():
    models = [{"model_id": "host", "group": [6]}]
    pmap = {6: {"permission_instances_map": {"host": ["View"]}}}
    ModelViewSet.model_add_permission(models, permission_instances_map=pmap, default_group=1)
    assert models[0]["permission"] == ["View"]


@pytest.mark.django_db
def test_get_model_info_denied_when_name_permission_only_exists_in_other_org(superuser, monkeypatch):
    from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil as PermissionUtil

    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info",
        lambda model_id: {"model_id": "host", "model_name": "主机", "group": [9]},
    )
    monkeypatch.setattr(f"{VIEWS}.CmdbRulesFormatUtil.has_object_permission", PermissionUtil.has_object_permission)
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda *a, **k: {6: {"permission_instances_map": {"host": ["View"]}, "inst_names": ["host"]}},
    )
    monkeypatch.setattr(f"{VIEWS}.ModelViewSet.organizations", lambda self, r, m: [9])
    response = ModelViewSet.as_view({"get": "get_model_info"})(_req("get", superuser), model_id="host")
    assert response.status_code == status.HTTP_403_FORBIDDEN
```

- [ ] **Step 2: Run the focused model tests to verify they fail**

Run: `cd server && uv run pytest apps/cmdb/tests/test_model_views.py -k "same_model_id_other_org or same_model_id_same_org_allowed or other_org" -v`

Expected: FAIL because `model_add_permission()` and the model detail path still accept a same-`model_id` permission that came from another organization.

- [ ] **Step 3: Implement the minimal model backfill fix**

```python
# server/apps/cmdb/views/model.py
group_instances_map = CmdbRulesFormatUtil.format_organizations_instances_map(permission_instances_map)
for model_info in model_list:
    model_info["permission"] = []
    groups = model_info["group"]

    for group in groups:
        if group == default_group and VIEW not in model_info["permission"]:
            model_info["permission"].append(VIEW)
        if group not in group_instances_map:
            continue
        for _permission in group_instances_map[group]["permission"]:
            if _permission not in model_info["permission"]:
                model_info["permission"].append(_permission)

    model_permission = group_instances_map.get(model_info["model_id"])
    if model_permission and set(groups) & set(model_permission["organization"]):
        for _permission in model_permission["permission"]:
            if _permission not in model_info["permission"]:
                model_info["permission"].append(_permission)
```

- [ ] **Step 4: Run the focused model tests to verify they pass**

Run: `cd server && uv run pytest apps/cmdb/tests/test_model_views.py -k "same_model_id_other_org or same_model_id_same_org_allowed or other_org" -v`

Expected: PASS with model permission backfill and representative detail denial scoped to matching organizations only.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/views/model.py \
        server/apps/cmdb/tests/test_model_views.py
git commit -m "fix: restrict cmdb model permission backfill"
```

## Final Verification

- [ ] **Run the focused CMDB permission regression suite**

```bash
cd server && uv run pytest \
    apps/cmdb/tests/test_permission_util.py \
    apps/cmdb/tests/test_misc_views.py \
    apps/cmdb/tests/test_instance_views.py \
    apps/cmdb/tests/test_model_views.py -v
```

Expected: PASS with helper, mixin, instance view, and model view regressions all green.

- [ ] **Run the standard server test entry if the focused suite passes**

```bash
cd server && make test
```

Expected: PASS, or if the repository baseline is already red, isolate and record any unrelated pre-existing failures before proceeding.

## Self-Review

1. **Spec coverage:** The plan covers helper-level final permission checks, instance/model permission backfill, representative detail-path denials, and the focused regression files named in the approved design spec.
2. **Placeholder scan:** No `TBD`, `TODO`, “similar to previous task”, or content-free “write tests” steps remain.
3. **Type consistency:** The same names are used throughout: `permission_instances_map`, `organization`, `group`, `has_object_permission()`, `add_instance_permission()`, and `model_add_permission()`.
