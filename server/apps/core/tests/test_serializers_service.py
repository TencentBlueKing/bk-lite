import pydantic.root_model  # noqa

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import serializers

from apps.core.utils import serializers as core_ser
from apps.core.utils.serializers import AuthSerializer, TeamSerializer, UsernameSerializer
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db

class _Obj:
    """轻量对象，模拟带 created_by/updated_by/team/id 的 DRF instance。"""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _make_serializer_cls(base, method_field=None, fields=None, **extra):
    """动态生成一个把 _Obj 的字段透传出去的子类，避免依赖具体 Model Meta。"""
    base_fields = fields if fields is not None else ["created_by", "updated_by", "domain", "updated_by_domain", "id", "team"]
    meta_fields = list(base_fields) + ([method_field] if method_field else [])

    if fields is None:
        class _S(base):
            created_by = serializers.CharField(required=False)
            updated_by = serializers.CharField(required=False)
            domain = serializers.CharField(required=False)
            updated_by_domain = serializers.CharField(required=False)
            id = serializers.IntegerField(required=False)
            team = serializers.ListField(required=False)

            class Meta:
                model = User
                fields = meta_fields
    else:
        class Meta:
            model = User
            fields = meta_fields

        field_factories = {
            "created_by": lambda: serializers.CharField(required=False),
            "updated_by": lambda: serializers.CharField(required=False),
            "domain": lambda: serializers.CharField(required=False),
            "updated_by_domain": lambda: serializers.CharField(required=False),
            "id": lambda: serializers.IntegerField(required=False),
            "team": lambda: serializers.ListField(required=False),
        }
        attrs = {"Meta": Meta, "__module__": __name__}
        for name in meta_fields:
            factory = field_factories.get(name)
            if factory is not None:
                attrs[name] = factory()
        _S = type("_S", (base,), attrs)

    for k, v in extra.items():
        setattr(_S, k, v)
    return _S


def _user_selects(ctx):
    table = User._meta.db_table
    return [query["sql"] for query in ctx.captured_queries if query["sql"].lstrip().upper().startswith("SELECT") and table in query["sql"]]


class TestUsernameSerializer:
    def test_maps_created_by_to_display_name(self):
        User.objects.create(username="alice", display_name="Alice Liddell", domain="domain.com", email="a@x.com")
        S = _make_serializer_cls(UsernameSerializer)
        obj = _Obj(created_by="alice", domain="domain.com", updated_by=None, id=1, team=[])
        data = S(obj).data
        assert data["created_by"] == "Alice Liddell"

    def test_unknown_user_keeps_raw_username(self):
        S = _make_serializer_cls(UsernameSerializer)
        obj = _Obj(created_by="ghost", domain="domain.com", updated_by=None, id=1, team=[])
        data = S(obj).data
        assert data["created_by"] == "ghost"

    def test_updated_by_uses_updated_by_domain(self):
        User.objects.create(username="bob", display_name="Bob B", domain="corp.com", email="b@x.com")
        S = _make_serializer_cls(UsernameSerializer)
        obj = _Obj(created_by=None, updated_by="bob", updated_by_domain="corp.com", id=1, team=[])
        data = S(obj).data
        assert data["updated_by"] == "Bob B"

    def test_skips_user_query_when_fields_omit_authors(self):
        User.objects.create(username="alice", display_name="Alice Liddell", domain="domain.com", email="a@x.com")
        S = _make_serializer_cls(UsernameSerializer, fields=["id", "team"])
        obj = _Obj(created_by="alice", domain="domain.com", updated_by=None, id=1, team=[])
        with CaptureQueriesContext(connection) as ctx:
            S(obj)
        assert _user_selects(ctx) == []

    @pytest.mark.parametrize("unrelated_count", [1, 10, 100])
    def test_author_lookup_query_count_does_not_grow_with_unrelated_users(self, unrelated_count):
        User.objects.bulk_create(
            [
                User(username=f"noise_{index}", display_name=f"Noise {index}", domain="domain.com", email=f"n{index}@x.com", password="")
                for index in range(unrelated_count)
            ]
        )
        User.objects.create(username="alice", display_name="Alice Page", domain="domain.com", email="alice@x.com")
        S = _make_serializer_cls(UsernameSerializer)
        obj = _Obj(created_by="alice", domain="domain.com", updated_by=None, id=1, team=[])
        with CaptureQueriesContext(connection) as ctx:
            serializer = S([obj], many=True)
            payload = serializer.data
        selects = _user_selects(ctx)
        assert len(selects) == 1
        assert "WHERE" in selects[0].upper()
        assert serializer.child.user_map == {"alice@domain.com": "Alice Page"}
        assert payload[0]["created_by"] == "Alice Page"

    def test_same_username_different_domain_maps_correctly(self):
        User.objects.create(username="alice", display_name="Alice Default", domain="domain.com", email="a1@x.com")
        User.objects.create(username="alice", display_name="Alice Corp", domain="corp.com", email="a2@x.com")
        S = _make_serializer_cls(UsernameSerializer)
        obj = _Obj(created_by="alice", domain="corp.com", updated_by=None, id=1, team=[])
        data = S(obj).data
        assert data["created_by"] == "Alice Corp"


class TestTeamSerializer:
    def test_team_name_resolves_known_ids(self, mocker):
        user = _Obj(group_list=[{"id": 1, "name": "Eng"}, {"id": 2, "name": "Ops"}])
        request = _Obj(user=user)
        S = _make_serializer_cls(TeamSerializer, method_field="team_name")
        obj = _Obj(created_by=None, updated_by=None, id=5, team=[1, 2, 99])
        data = S(obj, context={"request": request}).data
        # 99 不在 group_map 中被过滤
        assert data["team_name"] == ["Eng", "Ops"]


class TestAuthSerializer:
    def _build(self, mocker, permission_rules):
        mocker.patch.object(core_ser, "get_current_team", return_value="0")
        mocker.patch.object(core_ser, "get_permission_rules", return_value=permission_rules)
        user = _Obj(group_list=[])
        request = _Obj(user=user, COOKIES={})
        S = _make_serializer_cls(AuthSerializer, method_field="permissions", permission_key="test_key")
        return S, request

    def test_team_intersection_grants_view_operate(self, mocker):
        rules = {"team": [10, 20], "instance": []}
        S, request = self._build(mocker, rules)
        obj = _Obj(created_by=None, updated_by=None, id=1, team=[20, 30])
        data = S(obj, context={"request": request}).data
        assert data["permissions"] == ["View", "Operate"]

    def test_instance_rule_permission_returned(self, mocker):
        rules = {"team": [], "instance": [{"id": "7", "permission": ["View"]}]}
        S, request = self._build(mocker, rules)
        obj = _Obj(created_by=None, updated_by=None, id=7, team=[])
        data = S(obj, context={"request": request}).data
        assert data["permissions"] == ["View"]

    def test_instance_rule_merges_duplicate_ids(self, mocker):
        rules = {
            "team": [],
            "instance": [
                {"id": "7", "permission": ["View"]},
                {"id": "7", "permission": ["Operate"]},
            ],
        }
        S, request = self._build(mocker, rules)
        obj = _Obj(created_by=None, updated_by=None, id=7, team=[])
        data = S(obj, context={"request": request}).data
        assert set(data["permissions"]) == {"View", "Operate"}

    def test_default_permissions_when_no_rule(self, mocker):
        rules = {"team": [], "instance": []}
        S, request = self._build(mocker, rules)
        obj = _Obj(created_by=None, updated_by=None, id=999, team=[])
        data = S(obj, context={"request": request}).data
        assert data["permissions"] == ["View", "Operate"]

    def test_get_app_name_from_module_path(self, mocker):
        rules = {"team": [], "instance": []}
        S, request = self._build(mocker, rules)
        inst = S(context={"request": request})
        # 该测试模块路径 apps.core.tests... -> 提取 'core'
        assert inst.get_app_name() == "core"
