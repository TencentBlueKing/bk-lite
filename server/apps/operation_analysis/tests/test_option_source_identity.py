import json
from pathlib import Path

import pytest

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.services.option_source_identity import AMBIGUOUS, FORBIDDEN, MISSING, RESOLVED, resolve_option_source

SOURCE_API = Path(__file__).parents[1] / "support-files" / "source_api.json"
ASSOCIATION_API = "cmdb/get_model_association_options"
HOST_KEY = f"模型关联列表::{ASSOCIATION_API}"
BY_MODEL_NAME = "模型关联列表（按所选模型）"
BY_MODEL_REF = f"{BY_MODEL_NAME}::{ASSOCIATION_API}"
BY_MODEL_KEY = f"模型关联列表（按模型）::{ASSOCIATION_API}"


def _row(**kwargs):
    defaults = {
        "name": "自定义源",
        "rest_api": "custom/query",
        "source_type": "nats",
        "groups": [1],
        "is_build_in": False,
    }
    defaults.update(kwargs)
    return DataSourceAPIModel.objects.create(**defaults)


def test_latest_one_hop_seed_keeps_multiselect_relation():
    """最新 master 的一跳关系是多选空数组，不再带起点/终点条件。"""
    sources = {item["rest_api"]: item for item in json.loads(SOURCE_API.read_text(encoding="utf-8")) if item.get("rest_api")}
    one_hop = sources["cmdb/query_cmdb_one_hop"]
    relation = next(item for item in one_hop["params"] if item["name"] == "model_asst_id")
    names = [item["name"] for item in one_hop["params"]]
    assert relation["value"] == []
    assert relation["inputConfig"]["multiple"] is True
    assert relation["inputConfig"]["optionsSource"]["sourceRef"]["value"] == BY_MODEL_KEY
    assert "filters" not in names
    assert "end_filters" not in names


@pytest.mark.django_db
def test_rename_and_rest_api_change_keep_source_id():
    row = _row(name="关联选项", rest_api=ASSOCIATION_API)
    row.name = "关联选项-已改名"
    row.rest_api = "cmdb/renamed_association"
    row.save()
    result = resolve_option_source(source_id=row.id, current_team=1)
    assert result == {"status": RESOLVED, "id": row.id}


@pytest.mark.django_db
def test_same_api_copy_does_not_steal_binding():
    original = _row(name="模型关联列表（选项）", rest_api=ASSOCIATION_API)
    _row(name="模型关联列表（副本）", rest_api=ASSOCIATION_API)
    assert resolve_option_source(source_id=original.id, current_team=1)["id"] == original.id


@pytest.mark.django_db
def test_deleted_same_name_rebuild_does_not_take_over():
    row = _row(name="关联选项", rest_api=ASSOCIATION_API)
    old_id = row.id
    row.delete()
    _row(name="关联选项", rest_api=ASSOCIATION_API)
    assert resolve_option_source(source_id=old_id, current_team=1) == {"status": MISSING}


@pytest.mark.django_db
def test_forbidden_id_does_not_fall_back_to_another_row():
    hidden = _row(name="别的组织", rest_api=ASSOCIATION_API, groups=[9])
    _row(name="当前组织", rest_api=ASSOCIATION_API, groups=[1])
    assert resolve_option_source(source_id=hidden.id, current_team=1) == {"status": FORBIDDEN}


@pytest.mark.django_db
def test_superuser_still_forbidden_when_org_cannot_query():
    """解析成功必须能取数。超级用户看不见别的组织时，不能先解析成 resolved。"""
    hidden = _row(name="别的组织", rest_api=ASSOCIATION_API, groups=[9])
    visible = _row(name="当前组织", rest_api=ASSOCIATION_API, groups=[1])
    assert resolve_option_source(
        source_id=hidden.id,
        current_team=1,
        is_superuser=True,
    ) == {"status": FORBIDDEN}
    assert resolve_option_source(source_id=visible.id, current_team=1, is_superuser=True)["id"] == visible.id


@pytest.mark.django_db
def test_existing_invisible_id_does_not_restore_another_builtin():
    hidden = _row(
        name="别的组织内置",
        rest_api=ASSOCIATION_API,
        groups=[9],
        is_build_in=True,
        build_in_key=HOST_KEY,
    )
    other = _row(
        name="当前组织另一把钥匙",
        rest_api="cmdb/other",
        groups=[],
        is_build_in=True,
        build_in_key="other::key",
    )
    assert resolve_option_source(
        source_id=hidden.id,
        builtin_key="other::key",
        current_team=1,
        is_superuser=True,
    ) == {"status": FORBIDDEN}
    assert other.id != hidden.id


@pytest.mark.django_db
def test_builtin_recreate_restores_by_key_only():
    original = _row(
        name="模型关联列表（选项）",
        rest_api=ASSOCIATION_API,
        is_build_in=True,
        build_in_key=HOST_KEY,
        groups=[],
    )
    old_id = original.id
    original.delete()
    _row(name="用户副本", rest_api=ASSOCIATION_API, groups=[1])
    restored = _row(
        name="模型关联列表（选项）",
        rest_api=ASSOCIATION_API,
        is_build_in=True,
        build_in_key=HOST_KEY,
        groups=[],
    )
    result = resolve_option_source(source_id=old_id, builtin_key=HOST_KEY, current_team=1)
    assert result == {"status": RESOLVED, "id": restored.id}


@pytest.mark.django_db
def test_legacy_name_key_unique_even_if_path_is_shared():
    host = _row(
        name="模型关联列表（选项）",
        rest_api=ASSOCIATION_API,
        is_build_in=True,
        build_in_key=HOST_KEY,
        groups=[],
    )
    by_model = _row(
        name=BY_MODEL_NAME,
        rest_api=ASSOCIATION_API,
        is_build_in=True,
        build_in_key=f"模型关联列表（按模型）::{ASSOCIATION_API}",
        groups=[],
    )
    result = resolve_option_source(source_ref=BY_MODEL_REF, current_team=1)
    assert result == {"status": RESOLVED, "id": by_model.id}
    assert result["id"] != host.id


@pytest.mark.django_db
def test_legacy_bare_path_is_ambiguous_when_any_row_exists_outside_org():
    visible = _row(name="看得见", rest_api=ASSOCIATION_API, groups=[1])
    _row(name="看不见", rest_api=ASSOCIATION_API, groups=[9])
    result = resolve_option_source(source_ref=ASSOCIATION_API, current_team=1)
    assert result == {"status": AMBIGUOUS}
    assert "id" not in result
    assert visible.id


@pytest.mark.django_db
def test_legacy_unique_row_outside_org_is_forbidden_without_details():
    _row(name="看不见", rest_api="cmdb/get_room_list", groups=[9])
    result = resolve_option_source(source_ref="cmdb/get_room_list", current_team=1)
    assert result == {"status": FORBIDDEN}


@pytest.mark.django_db
def test_user_create_gets_new_portable_key_and_builtin_does_not():
    user = _row(name="用户源", rest_api="")
    builtin = _row(name="内置源", rest_api="cmdb/get_room_list", is_build_in=True, build_in_key="CMDB 机房列表::cmdb/get_room_list", groups=[])
    assert user.portable_key
    assert builtin.portable_key in (None, "")
    copy = _row(name="用户源副本", rest_api="")
    assert copy.portable_key and copy.portable_key != user.portable_key


@pytest.mark.django_db
def test_serializer_cannot_forge_portable_key(authenticated_user):
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.operation_analysis.serializers.datasource_serializers import DataSourceAPIModelSerializer

    request = APIRequestFactory().post("/operation_analysis/api/data_source/", data={}, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    request.user = authenticated_user
    force_authenticate(request, user=authenticated_user)
    serializer = DataSourceAPIModelSerializer(
        context={"request": request},
        data={
            "name": "custom",
            "rest_api": "custom/query",
            "source_type": "nats",
            "connection_config": {},
            "query_config": {},
            "params": [],
            "chart_type": ["single"],
            "field_schema": [],
            "groups": [1],
            "namespaces": [],
            "tag": [],
            "portable_key": "forged-key",
            "build_in_key": "forged",
            "is_build_in": True,
        },
    )
    assert serializer.is_valid(), serializer.errors
    assert "portable_key" not in serializer.validated_data
    saved = serializer.save()
    assert saved.portable_key and saved.portable_key != "forged-key"
    assert saved.is_build_in is False
    assert saved.build_in_key in (None, "")
