"""CMDB 统一网关测试共用身份与目录夹具。"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

from apps.base.models import User, UserAPISecret
from apps.cmdb.constants.constants import PERMISSION_MODEL
from apps.system_mgmt.models import Group, Menu, Role
from apps.system_mgmt.models import User as SystemUser

TEAM_A_UUID = "11111111-1111-4111-8111-111111111111"
TEAM_A2_UUID = "11111111-1111-4111-8111-111111111112"
TEAM_B_UUID = "22222222-2222-4222-8222-222222222222"

CMDB_OPENAPI_MENUS = [
    "model_management-View",
    "asset_info-View",
    "asset_info-Add",
    "asset_info-Edit",
    "asset_info-Delete",
    "asset_info-Add Associate",
    "asset_info-Delete Associate",
]


def auth(token):
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def grant_cmdb_openapi_menus(system_user):
    menu_ids = []
    for name in CMDB_OPENAPI_MENUS:
        menu, _ = Menu.objects.get_or_create(
            name=name,
            app="cmdb",
            defaults={"display_name": name, "url": "", "menu_type": "button"},
        )
        menu_ids.append(menu.id)
    role, _ = Role.objects.update_or_create(
        name=f"openapi-cmdb-{system_user.username}",
        app="cmdb",
        defaults={"menu_list": menu_ids},
    )
    system_user.role_list = [role.id]
    system_user.save(update_fields=["role_list"])
    return role


def make_tenant(*, team_name, username, domain):
    team = Group.objects.create(name=f"{team_name}-{uuid.uuid4().hex[:8]}")
    user = User.objects.create(username=f"{username}-{uuid.uuid4().hex[:8]}", domain=domain)
    system_user = SystemUser.objects.create(
        username=user.username,
        domain=user.domain,
        group_list=[team.id],
    )
    grant_cmdb_openapi_menus(system_user)
    token = UserAPISecret.generate_api_secret()
    UserAPISecret.objects.create(
        username=user.username,
        domain=user.domain,
        api_secret=UserAPISecret.hash_api_secret(token),
        team=team.id,
    )
    return SimpleNamespace(team=team, user=user, system_user=system_user, token=token)


def instance_row(*, inst_id, inst_uuid, model_id, inst_name, team_id, creator="api-user"):
    return {
        "_id": inst_id,
        "inst_uuid": inst_uuid,
        "model_id": model_id,
        "inst_name": inst_name,
        "organization": [team_id],
        "_creator": creator,
        "_labels": "instance",
    }


def start_cmdb_gateway_catalog(tenants):  # noqa: C901
    store = {
        tenants.a.team.id: [
            instance_row(
                inst_id=11,
                inst_uuid=TEAM_A_UUID,
                model_id="host",
                inst_name="host-a",
                team_id=tenants.a.team.id,
                creator=tenants.a.user.username,
            ),
            instance_row(
                inst_id=13,
                inst_uuid=TEAM_A2_UUID,
                model_id="host",
                inst_name="host-a2",
                team_id=tenants.a.team.id,
                creator=tenants.a.user.username,
            ),
        ],
        tenants.b.team.id: [
            instance_row(
                inst_id=12,
                inst_uuid=TEAM_B_UUID,
                model_id="host",
                inst_name="host-b",
                team_id=tenants.b.team.id,
                creator=tenants.b.user.username,
            ),
        ],
    }
    calls = SimpleNamespace(
        create=[],
        update=[],
        delete=[],
        batch_create=[],
        batch_update=[],
        association_create=[],
        association_delete=[],
    )
    default_group_id = 1

    def caller_teams(permissions_map):
        result = set()
        for team_id, payload in (permissions_map or {}).items():
            if isinstance(payload, dict) and "__default_model" in payload:
                continue
            result.add(int(team_id))
        return result

    def fake_search_model(language="en", permissions_map=None, include_hidden=False, **_kwargs):
        del language, include_hidden
        team_ids = caller_teams(permissions_map)
        rows = [{"model_id": "host", "classification_id": "class-common", "model_name": "Host"}]
        if tenants.a.team.id in team_ids:
            rows.append({"model_id": "host-a", "classification_id": "class-a", "model_name": "Host A"})
        if tenants.b.team.id in team_ids:
            rows.append({"model_id": "host-b", "classification_id": "class-b", "model_name": "Host B"})
        return rows

    def fake_search_model_info(model_id):
        catalog = {
            "host": {"model_id": "host", "is_visible": True},
            "host-a": {"model_id": "host-a", "is_visible": True},
            "host-b": {"model_id": "host-b", "is_visible": True},
        }
        return catalog.get(model_id)

    def fake_has_object_permission(obj_type, operator=None, model_id=None, permission_instances_map=None, instance=None, **_kwargs):
        if obj_type == PERMISSION_MODEL:
            if model_id == "host":
                return True
            team_ids = caller_teams(permission_instances_map)
            if model_id == "host-a":
                return tenants.a.team.id in team_ids
            if model_id == "host-b":
                return tenants.b.team.id in team_ids
            return False
        return True

    def fake_query_entity_by_uuid(inst_uuid):
        key = str(inst_uuid)
        for rows in store.values():
            for row in rows:
                if row["inst_uuid"] == key:
                    return dict(row)
        return {}

    def fake_instance_create(model_id, data, operator, allowed_org_ids=None):
        created = {
            "inst_uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "model_id": model_id,
            "inst_name": data.get("inst_name"),
            "organization": list(data.get("organization") or []),
            "_creator": operator,
        }
        calls.create.append(
            {
                "model_id": model_id,
                "data": dict(data),
                "operator": operator,
                "allowed_org_ids": list(allowed_org_ids or []),
            }
        )
        return created

    def fake_instance_update(user_groups, roles, inst_uuid, data, operator, allowed_org_ids=None):
        del user_groups, roles
        key = str(inst_uuid)
        calls.update.append(
            {
                "inst_uuid": key,
                "data": dict(data),
                "operator": operator,
                "allowed_org_ids": list(allowed_org_ids or []),
            }
        )
        for rows in store.values():
            for row in rows:
                if row["inst_uuid"] == key:
                    row.update(data)
                    return dict(row)
        return {}

    def fake_batch_delete(user_groups, roles, inst_uuids, operator):
        del user_groups, roles, operator
        keys = [str(item) for item in inst_uuids]
        calls.delete.append(keys)
        for team_id, rows in list(store.items()):
            store[team_id] = [row for row in rows if row["inst_uuid"] not in keys]

    def fake_batch_create(model_id, items, operator, allowed_org_ids=None):
        created = []
        for index, item in enumerate(items):
            created.append(
                {
                    "inst_uuid": f"bbbbbbbb-bbbb-4bbb-8bbb-{index:012d}",
                    "model_id": model_id,
                    "inst_name": item.get("inst_name"),
                    "organization": list(item.get("organization") or []),
                    "_creator": operator,
                }
            )
        calls.batch_create.append(
            {
                "model_id": model_id,
                "items": list(items),
                "operator": operator,
                "allowed_org_ids": list(allowed_org_ids or []),
            }
        )
        return created

    def fake_batch_update(user_groups, roles, inst_uuids, update_data, operator, allowed_org_ids=None):
        del user_groups, roles
        keys = [str(item) for item in inst_uuids]
        calls.batch_update.append(
            {
                "inst_uuids": keys,
                "update_data": dict(update_data),
                "operator": operator,
                "allowed_org_ids": list(allowed_org_ids or []),
            }
        )
        updated = []
        for rows in store.values():
            for row in rows:
                if row["inst_uuid"] in keys:
                    row.update(update_data)
                    updated.append(dict(row))
        return updated

    def fake_list_associations(model_id, inst_uuid, business_only=True):
        del model_id, business_only
        if str(inst_uuid) != TEAM_A_UUID:
            return []
        return [
            {
                "model_asst_id": "host_run_host",
                "inst_list": [dict(store[tenants.a.team.id][1])],
            }
        ]

    def fake_association_create(**kwargs):
        calls.association_create.append(dict(kwargs))
        return {"model_asst_id": kwargs["model_asst_id"], "src_inst_uuid": kwargs["src_inst_uuid"], "dst_inst_uuid": kwargs["dst_inst_uuid"]}

    def fake_association_delete(**kwargs):
        calls.association_delete.append(dict(kwargs))
        return {"deleted": True}

    patches = [
        patch("apps.cmdb.open_api.services.get_default_group_id", return_value=[default_group_id]),
        patch("apps.cmdb.open_api.services.ModelManage.search_model", side_effect=fake_search_model),
        patch("apps.cmdb.open_api.services.ModelManage.search_model_info", side_effect=fake_search_model_info),
        patch(
            "apps.cmdb.open_api.services.ModelManage.search_model_attr",
            return_value=[{"attr_id": "inst_name", "attr_type": "str", "editable": True, "is_required": True}],
        ),
        patch(
            "apps.cmdb.open_api.services.ClassificationManage.search_model_classification",
            return_value=[
                {"classification_id": "class-a", "classification_name": "Class A"},
                {"classification_id": "class-b", "classification_name": "Class B"},
                {"classification_id": "class-common", "classification_name": "Common"},
            ],
        ),
        patch(
            "apps.cmdb.open_api.services.ModelManage.model_association_search",
            return_value=[{"model_asst_id": "host_run_host", "src_model_id": "host", "dst_model_id": "host"}],
        ),
        patch(
            "apps.cmdb.open_api.services.ModelManage.model_association_info_search",
            side_effect=lambda asst_id: (
                {"model_asst_id": asst_id, "src_model_id": "host", "dst_model_id": "host"} if asst_id == "host_run_host" else {}
            ),
        ),
        patch("apps.cmdb.open_api.services.CmdbRulesFormatUtil.has_object_permission", side_effect=fake_has_object_permission),
        patch("apps.cmdb.open_api.auth.get_permission_rules", return_value={"team": []}),
        patch("apps.cmdb.open_api.services.InstanceManage.query_entity_by_uuid", side_effect=fake_query_entity_by_uuid),
        patch("apps.cmdb.open_api.services.InstanceManage.instance_create", side_effect=fake_instance_create),
        patch("apps.cmdb.open_api.services.InstanceManage.instance_update_by_uuid", side_effect=fake_instance_update),
        patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_delete_by_uuids", side_effect=fake_batch_delete),
        patch("apps.cmdb.open_api.services.InstanceManage.instance_batch_create", side_effect=fake_batch_create),
        patch("apps.cmdb.open_api.services.InstanceManage.batch_instance_update_by_uuids", side_effect=fake_batch_update),
        patch(
            "apps.cmdb.open_api.services.InstanceManage.instance_association_instance_list_by_uuid",
            side_effect=fake_list_associations,
        ),
        patch(
            "apps.cmdb.open_api.services.InstanceManage.instance_association_create_by_uuid",
            side_effect=fake_association_create,
        ),
        patch(
            "apps.cmdb.open_api.services.InstanceManage.instance_association_delete_by_key",
            side_effect=fake_association_delete,
        ),
    ]
    for item in patches:
        item.start()
    return SimpleNamespace(store=store, calls=calls, patches=patches)


def stop_cmdb_gateway_catalog(catalog):
    for item in catalog.patches:
        item.stop()
