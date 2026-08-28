from types import SimpleNamespace

import pytest
from django.test import RequestFactory
from rest_framework.exceptions import ValidationError

from apps.system_mgmt.serializers.channel_serializer import ChannelSerializer
from apps.system_mgmt.serializers.custom_menu_group_serializer import CustomMenuGroupSerializer
from apps.system_mgmt.serializers.network_white_list_serializer import NetworkWhiteListSerializer
from apps.system_mgmt.utils.password_validator import PasswordValidator
from apps.system_mgmt.viewset.custom_menu_group_viewset import CustomMenuGroupViewSet
from apps.system_mgmt.viewset.group_data_rule_viewset import GroupDataRuleViewSet
from apps.system_mgmt.viewset.group_viewset import GroupViewSet
from apps.system_mgmt.viewset.role_viewset import RoleViewSet
from apps.system_mgmt.viewset.user_viewset import UserViewSet


def request_with_locale(locale):
    request = RequestFactory().post("/system_mgmt/api/")
    request.user = SimpleNamespace(locale=locale)
    return request


def response_message(response):
    import json

    return json.loads(response.content)["message"]


def response_payload(response):
    import json

    return json.loads(response.content)


def test_user_disabled_endpoint_uses_request_locale():
    response = UserViewSet().list(request_with_locale("en"))
    assert response.status_code == 405
    assert response_payload(response) == {"result": False, "message": "API is not enabled"}


def test_update_user_passes_request_locale_to_synced_group_validation(monkeypatch):
    request = request_with_locale("zh-Hans")
    request.data = {"user_id": 1, "groups": [1], "roles": [], "username": "local-user"}
    target_user = SimpleNamespace(sync_source_id=None, group_list=[1])
    monkeypatch.setattr("apps.system_mgmt.viewset.user_viewset.User.objects.get", lambda **kwargs: target_user)
    monkeypatch.setattr(UserViewSet, "_validate_target_user_permission", lambda self, request, user: (True, None))
    monkeypatch.setattr("apps.system_mgmt.viewset.user_viewset._validate_selected_groups", lambda groups, loader: None)
    monkeypatch.setattr("apps.system_mgmt.viewset.user_viewset._normalize_group_ids", lambda groups: (groups, []))
    monkeypatch.setattr(
        "apps.system_mgmt.viewset.user_viewset._validate_local_user_group_changes",
        lambda groups, existing_groups=None, loader=None: loader.get("error.synced_group_membership_immutable")
        if loader
        else "Synced group membership cannot be changed locally",
    )

    action = UserViewSet().update_user.__wrapped__
    response = action(UserViewSet(), request)

    assert response.status_code == 200
    assert response_payload(response) == {"result": False, "message": "同步组织成员关系不能在本地修改"}


@pytest.mark.parametrize(
    ("locale", "expected"),
    [("en", "Password is required"), ("zh-Hans", "密码不能为空")],
)
def test_password_validator_uses_requested_locale(locale, expected):
    assert PasswordValidator.validate_password_with_config("", {}, locale=locale) == (False, expected)


@pytest.mark.parametrize(
    ("locale", "users", "expected"),
    [
        ("en", [], "No users available to import"),
        ("zh-Hans", [], "没有可导入的用户数据"),
        ("en", [{}] * 501, "You can import at most 500 users at a time"),
        ("zh-Hans", [{}] * 501, "单次最多导入 500 名用户"),
    ],
)
def test_import_users_boundary_messages_use_request_locale(locale, users, expected):
    request = request_with_locale(locale)
    request.data = {"group_id": 1, "users": users, "file_name": "users.xlsx"}
    response = UserViewSet.import_users.__wrapped__(UserViewSet(), request)
    assert response.status_code == 400
    assert response_payload(response) == {"result": False, "message": expected}


def _stub_import_users_group_lookup(monkeypatch):
    monkeypatch.setattr("apps.system_mgmt.viewset.user_viewset._validate_selected_groups", lambda groups, loader: None)
    monkeypatch.setattr("apps.system_mgmt.viewset.user_viewset._normalize_group_ids", lambda groups: ([1], []))
    monkeypatch.setattr(UserViewSet, "_validate_group_scope_for_request", lambda self, request, groups, loader: None)
    monkeypatch.setattr(
        "apps.system_mgmt.viewset.user_viewset.GroupUtils.active_queryset",
        lambda: SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(first=lambda: SimpleNamespace(id=1, name="org"))),
    )
    monkeypatch.setattr(
        "apps.system_mgmt.viewset.user_viewset.SystemSettings.objects.filter",
        lambda **kwargs: SimpleNamespace(values_list=lambda *args, **kw: []),
    )
    monkeypatch.setattr("apps.system_mgmt.viewset.user_viewset.log_operation", lambda *args, **kwargs: None)


@pytest.mark.parametrize(
    ("locale", "users", "expected"),
    [
        ("en", ["not-a-row"], "Invalid data format"),
        ("zh-Hans", ["not-a-row"], "数据格式不正确"),
        ("en", [{"username": "", "lastName": "A", "email": "a@example.com"}], "Required fields are missing"),
        ("zh-Hans", [{"username": "", "lastName": "A", "email": "a@example.com"}], "缺少必填字段"),
        ("en", [{"username": "bad-phone", "lastName": "A", "email": "a@example.com", "phone": "abc"}], "Invalid phone number format"),
        ("zh-Hans", [{"username": "bad-phone", "lastName": "A", "email": "a@example.com", "phone": "abc"}], "手机号格式不正确"),
        ("en", [{"username": "bad-email", "lastName": "A", "email": "not-an-email"}], "Invalid email format"),
        ("zh-Hans", [{"username": "bad-email", "lastName": "A", "email": "not-an-email"}], "邮箱格式不正确"),
        ("en", [{"username": "existing", "lastName": "A", "email": "a@example.com"}], "Username already exists"),
        ("zh-Hans", [{"username": "existing", "lastName": "A", "email": "a@example.com"}], "用户名已存在"),
    ],
)
def test_import_users_row_messages_use_request_locale(monkeypatch, locale, users, expected):
    _stub_import_users_group_lookup(monkeypatch)
    monkeypatch.setattr(
        "apps.system_mgmt.viewset.user_viewset.User.objects.filter",
        lambda **kwargs: SimpleNamespace(exists=lambda: kwargs.get("username") == "existing"),
    )
    request = request_with_locale(locale)
    request.data = {"group_id": 1, "users": users, "file_name": "users.xlsx"}
    response = UserViewSet.import_users.__wrapped__(UserViewSet(), request)
    payload = response_payload(response)
    assert response.status_code == 200
    assert payload["result"] is True
    assert payload["data"]["failures"][0]["message"] == expected


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "Failed to create user"),
        ("zh-Hans", "创建用户失败"),
    ],
)
def test_import_users_create_failed_uses_request_locale(monkeypatch, locale, expected):
    class Atomic:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    _stub_import_users_group_lookup(monkeypatch)
    monkeypatch.setattr(
        "apps.system_mgmt.viewset.user_viewset.User.objects.filter",
        lambda **kwargs: SimpleNamespace(exists=lambda: False),
    )
    monkeypatch.setattr("apps.system_mgmt.viewset.user_viewset.transaction.atomic", Atomic)
    monkeypatch.setattr("apps.system_mgmt.viewset.user_viewset.logger.exception", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "apps.system_mgmt.viewset.user_viewset.User.objects.create",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("create failed")),
    )
    request = request_with_locale(locale)
    request.data = {
        "group_id": 1,
        "file_name": "users.xlsx",
        "users": [{"username": "new-import-user", "lastName": "A", "email": "a@example.com"}],
    }
    response = UserViewSet.import_users.__wrapped__(UserViewSet(), request)
    payload = response_payload(response)
    assert response.status_code == 200
    assert payload["result"] is True
    assert payload["data"]["failures"] == [
        {"row_number": 2, "username": "new-import-user", "message": expected},
    ]


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "Password policy:"),
        ("zh-Hans", "密码策略要求："),
    ],
)
def test_password_policy_description_uses_requested_locale(monkeypatch, locale, expected):
    monkeypatch.setattr(
        PasswordValidator,
        "get_password_settings",
        staticmethod(lambda: {
            "min_length": 8,
            "max_length": 20,
            "required_char_types": ["uppercase", "lowercase", "digit", "special"],
        }),
    )
    description = PasswordValidator.get_password_policy_description(locale=locale)
    assert expected in description
    assert "8-20" in description
    if locale == "zh-Hans":
        assert "必须包含：大写字母, 小写字母, 数字, 特殊符号" in description
    else:
        assert "Must contain: uppercase letter, lowercase letter, number, special character" in description


@pytest.mark.parametrize(
    ("locale", "config", "path", "expected"),
    [
        ("en", "not-an-object", ("config",), "NATS config must be an object"),
        ("zh-Hans", "not-an-object", ("config",), "NATS 配置必须是对象"),
        ("en", {"supports_notify_person": "true"}, ("config", "supports_notify_person"), "must be a boolean"),
        ("zh-Hans", {"supports_notify_person": "true"}, ("config", "supports_notify_person"), "必须是布尔值"),
        ("en", {"nats_mode": "unknown-mode"}, ("config", "nats_mode"), "unsupported NATS extension mode"),
        ("zh-Hans", {"nats_mode": "unknown-mode"}, ("config", "nats_mode"), "不支持的 NATS 扩展模式"),
    ],
)
def test_nats_config_validation_uses_requested_locale(locale, config, path, expected):
    serializer = object.__new__(ChannelSerializer)
    serializer.parent = None
    serializer._context = {"request": request_with_locale(locale)}
    with pytest.raises(ValidationError) as exc_info:
        serializer.validate_nats_config(config)
    detail = exc_info.value.detail
    for key in path:
        detail = detail[key]
    assert str(detail) == expected


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "notification topic identifier is already in use"),
        ("zh-Hans", "通知主题标识已被使用"),
    ],
)
def test_nats_subject_key_unique_uses_requested_locale(monkeypatch, locale, expected):
    class DuplicateSubjectQuerySet:
        def exclude(self, **kwargs):
            return self

        def exists(self):
            return True

    monkeypatch.setattr(
        "apps.system_mgmt.serializers.channel_serializer.nats_notifications",
        SimpleNamespace(handles_config=lambda config: True),
    )
    monkeypatch.setattr(
        "apps.system_mgmt.serializers.channel_serializer.Channel.objects.filter",
        lambda **kwargs: DuplicateSubjectQuerySet(),
    )
    serializer = object.__new__(ChannelSerializer)
    serializer.parent = None
    serializer._context = {"request": request_with_locale(locale)}
    with pytest.raises(ValidationError) as exc_info:
        serializer.validate_nats_subject_key_unique({"subject_key": "customer-alerts"})
    assert str(exc_info.value.detail["config"]["subject_key"]) == expected


@pytest.mark.parametrize(
    ("serializer_class", "input_value", "expected"),
    [
        (ChannelSerializer, None, "Please select the channel organization"),
        (NetworkWhiteListSerializer, "", "Network cannot be empty"),
    ],
)
def test_serializer_validation_uses_request_locale(serializer_class, input_value, expected):
    if serializer_class is ChannelSerializer:
        serializer = object.__new__(ChannelSerializer)
        serializer.parent = None
        serializer._context = {"request": request_with_locale("en")}
    else:
        serializer = serializer_class(context={"request": request_with_locale("en")})
    validator = serializer.validate_team if serializer_class is ChannelSerializer else serializer.validate_network
    with pytest.raises(ValidationError) as exc_info:
        validator(input_value)
    assert str(exc_info.value.detail[0]) == expected


def test_custom_menu_group_serializer_uses_request_locale(monkeypatch):
    class ExistingMenuGroupQuerySet:
        def exists(self):
            return True

    monkeypatch.setattr(
        "apps.system_mgmt.serializers.custom_menu_group_serializer.CustomMenuGroup.objects.filter",
        lambda **kwargs: ExistingMenuGroupQuerySet(),
    )
    serializer = object.__new__(CustomMenuGroupSerializer)
    serializer.parent = None
    serializer._context = {"request": request_with_locale("en")}
    serializer.instance = None
    with pytest.raises(ValidationError) as exc_info:
        serializer.validate({"app": "cmdb", "display_name": "Menu", "is_enabled": False})
    assert str(exc_info.value.detail[0]) == "A menu group with the same display name already exists under app cmdb"


def test_custom_menu_group_missing_app_uses_request_locale():
    view = CustomMenuGroupViewSet()
    response = view.get_menus(request_with_locale("en"))
    assert response.status_code == 400
    assert response_payload(response) == {"result": False, "message": "App parameter is required"}


def test_custom_menu_group_menu_tree_preserves_data_shape(monkeypatch):
    menu_group = SimpleNamespace(is_build_in=False, menus=[{"id": 1, "name": "overview"}])
    monkeypatch.setattr(
        "apps.system_mgmt.viewset.custom_menu_group_viewset.CustomMenuGroup.objects.filter",
        lambda **kwargs: SimpleNamespace(first=lambda: menu_group),
    )
    request = RequestFactory().get("/system_mgmt/api/custom-menu-group/get_menus/?app=cmdb")
    request.user = SimpleNamespace(locale="en")

    response = CustomMenuGroupViewSet().get_menus(request)

    assert response.status_code == 200
    assert response_payload(response) == {
        "result": True,
        "data": {"is_build_in": False, "menus": [{"id": 1, "name": "overview"}]},
        "message": "Success",
    }


def test_group_data_rule_disabled_endpoint_uses_request_locale():
    view = GroupDataRuleViewSet()
    view.loader = None
    response = view.retrieve(request_with_locale("en"))
    assert response.status_code == 405
    assert response_payload(response) == {"result": False, "message": "API is not enabled"}


def test_group_invalid_group_ids_uses_request_locale():
    view = GroupViewSet()
    view.loader = None
    request = request_with_locale("en")
    request.data = {"group_ids": "not-a-list"}
    action = view.batch_get_group_detail_with_roles.__wrapped__
    response = action(view, request)
    assert response.status_code == 400
    assert response_payload(response) == {"result": False, "message": "group_ids must be a required list"}


def test_role_group_scope_fallback_uses_request_locale(monkeypatch):
    monkeypatch.setattr("apps.system_mgmt.viewset.role_viewset.get_unauthorized_group_ids", lambda user, group_ids: {1})
    view = RoleViewSet()
    view.loader = None
    response = view._validate_group_scope_for_request(request_with_locale("en"), [1])
    assert response.status_code == 403
    assert response_payload(response) == {"result": False, "message": "You do not have permission to access this group."}
