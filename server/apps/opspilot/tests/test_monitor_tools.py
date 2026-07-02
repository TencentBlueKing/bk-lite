import pytest
from django.contrib.auth.hashers import make_password

from apps.core.mixinx import EncryptMixin


@pytest.mark.django_db
def test_monitor_authenticate_context_uses_user_group_first(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.system_mgmt.models import User

    user = User.objects.create(
        username="alice",
        password=make_password("secret"),
        domain="domain.com",
        group_list=[{"id": 12, "name": "Team 12"}],
    )

    context = utils.authenticate_monitor_user(username="alice", password="secret")

    assert context["user"] == user.username
    assert context["domain"] == user.domain
    assert context["team"] == 12
    assert context["include_children"] is False


@pytest.mark.django_db
def test_monitor_authenticate_context_uses_explicit_team_id(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.system_mgmt.models import User

    user = User.objects.create(
        username="alice",
        password=make_password("secret"),
        domain="domain.com",
        group_list=[{"id": 12, "name": "Team 12"}],
    )

    context = utils.authenticate_monitor_user(username="alice", password="secret", team_id=33)

    assert context["user"] == user.username
    assert context["domain"] == user.domain
    assert context["team"] == 33
    assert context["include_children"] is False


@pytest.mark.django_db
def test_monitor_authenticate_context_uses_explicit_domain(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.system_mgmt.models import User

    user = User.objects.create(
        username="alice",
        password=make_password("secret"),
        domain="tenant-a.com",
        group_list=[{"id": 12, "name": "Team 12"}],
    )

    context = utils.authenticate_monitor_user(username="alice", password="secret", domain="tenant-a.com")

    assert context["user"] == user.username
    assert context["domain"] == user.domain
    assert context["team"] == 12
    assert context["include_children"] is False


@pytest.mark.django_db
def test_monitor_authenticate_context_falls_back_to_default_group(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.system_mgmt.models import User

    User.objects.create(
        username="alice",
        password=make_password("secret"),
        domain="domain.com",
        group_list=[],
    )
    mocker.patch.object(utils, "get_default_group_id", return_value=[99])

    context = utils.authenticate_monitor_user(username="alice", password="secret")

    assert context["team"] == 99
    assert context["include_children"] is False


def test_monitor_authenticate_context_requires_username_and_password():
    from apps.opspilot.metis.llm.tools.monitor import utils

    with pytest.raises(ValueError, match="username is required"):
        utils.authenticate_monitor_user(username="", password="secret")

    with pytest.raises(ValueError, match="password is required"):
        utils.authenticate_monitor_user(username="alice", password="")


@pytest.mark.django_db
def test_monitor_authenticate_context_rejects_bad_password():
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.system_mgmt.models import User

    User.objects.create(
        username="alice",
        password=make_password("secret"),
        domain="domain.com",
        group_list=[{"id": 12, "name": "Team 12"}],
    )

    with pytest.raises(ValueError, match="Username or password is incorrect"):
        utils.authenticate_monitor_user(username="alice", password="bad")


@pytest.mark.django_db
def test_monitor_authenticate_context_accepts_encrypted_password():
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.system_mgmt.models import User

    User.objects.create(
        username="alice",
        password=make_password("secret"),
        domain="domain.com",
        group_list=[{"id": 12, "name": "Team 12"}],
    )
    encrypted = {"value": "secret"}
    EncryptMixin.encrypt_field("value", encrypted)

    context = utils.authenticate_monitor_user(username="alice", password=encrypted["value"])

    assert context["user"] == "alice"
    assert context["domain"] == "domain.com"
    assert context["team"] == 12


@pytest.mark.django_db
def test_monitor_call_rpc_wraps_success(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.system_mgmt.models import User

    user = User.objects.create(
        username="alice",
        password=make_password("secret"),
        domain="domain.com",
        group_list=[{"id": 12, "name": "Team 12"}],
    )
    rpc = mocker.Mock()
    rpc.monitor_objects.return_value = {"result": True, "data": [{"id": "host"}], "message": ""}
    rpc_cls = mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = utils.call_monitor_rpc("monitor_objects", username="alice", password="secret")

    assert result == {"success": True, "data": [{"id": "host"}]}
    rpc_cls.assert_called_once_with()
    rpc.monitor_objects.assert_called_once_with(user_info={"user": user.username, "domain": user.domain, "team": 12, "include_children": False})


@pytest.mark.django_db
def test_monitor_call_rpc_wraps_rpc_error(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.system_mgmt.models import User

    User.objects.create(
        username="alice",
        password=make_password("secret"),
        domain="domain.com",
        group_list=[{"id": 12, "name": "Team 12"}],
    )
    rpc = mocker.Mock()
    rpc.monitor_objects.side_effect = RuntimeError("rpc down")
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = utils.call_monitor_rpc("monitor_objects", username="alice", password="secret")

    assert result["success"] is False
    assert "rpc down" in result["error"]


def test_monitor_list_objects_uses_rpc_wrapper(mocker):
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_objects

    rpc_call = mocker.patch(
        "apps.opspilot.metis.llm.tools.monitor.objects.call_monitor_rpc",
        return_value={"success": True, "data": [{"id": "host"}]},
    )

    result = monitor_list_objects.invoke({"username": "alice", "password": "secret", "domain": "tenant-a.com"})

    assert result == {"success": True, "data": [{"id": "host"}]}
    rpc_call.assert_called_once_with("monitor_objects", username="alice", password="secret", domain="tenant-a.com", team_id=None)


def test_monitor_list_objects_uses_configurable_fallback_when_tool_args_missing(mocker):
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_objects

    rpc_call = mocker.patch(
        "apps.opspilot.metis.llm.tools.monitor.objects.call_monitor_rpc",
        return_value={"success": True, "data": [{"id": "host"}]},
    )

    result = monitor_list_objects.invoke(
        {},
        config={"configurable": {"username": "alice", "password": "secret", "domain": "tenant-a.com", "team_id": 88}},
    )

    assert result == {"success": True, "data": [{"id": "host"}]}
    rpc_call.assert_called_once_with("monitor_objects", username="alice", password="secret", domain="tenant-a.com", team_id=88)


def test_monitor_list_object_instances_passes_optional_team_id_only(mocker):
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_object_instances

    rpc_call = mocker.patch(
        "apps.opspilot.metis.llm.tools.monitor.objects.call_monitor_rpc",
        return_value={"success": True, "data": [{"id": "1"}]},
    )

    result = monitor_list_object_instances.invoke(
        {"monitor_obj_id": "host", "username": "alice", "password": "secret", "domain": "tenant-a.com", "team_id": 88}
    )

    assert result == {"success": True, "data": [{"id": "1"}]}
    kwargs = rpc_call.call_args.kwargs
    assert kwargs["monitor_obj_id"] == "host"
    assert kwargs["team_id"] == 88
    assert kwargs["username"] == "alice"
    assert kwargs["password"] == "secret"
    assert kwargs["domain"] == "tenant-a.com"
    assert "include_children" not in kwargs


def test_monitor_query_metric_data_requires_minimum_fields(mocker):
    from apps.opspilot.metis.llm.tools.monitor.metrics import monitor_query_metric_data

    rpc_call = mocker.patch("apps.opspilot.metis.llm.tools.monitor.metrics.call_monitor_rpc")

    result = monitor_query_metric_data.invoke(
        {
            "monitor_obj_id": "host",
            "metric": "cpu_usage",
            "username": "alice",
            "password": "secret",
        }
    )

    assert result["success"] is False
    assert "start is required" in result["error"]
    rpc_call.assert_not_called()


def test_monitor_not_in_static_tools_loader_metadata():
    """monitor 是 builtin 工具（经 build_builtin_monitor_tool 注册），

    刻意不挂在 ToolsLoader.TOOL_MODULES 静态映射里，因此 get_all_tools_metadata
    不应包含 monitor 类别。回归这一隔离边界，避免 monitor 被重复登记到通用 loader。
    """
    from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader

    assert "monitor" not in ToolsLoader.TOOL_MODULES

    metadata = ToolsLoader.get_all_tools_metadata()
    names = {item["name"] for item in metadata}
    assert "monitor" not in names


def test_builtin_monitor_tool_descriptor_shape():
    """build_builtin_monitor_tool 产出的描述符须带 builtin 标记、langchain url 与子工具。"""
    from apps.core.utils.loader import LanguageLoader
    from apps.opspilot.services import builtin_tools

    loader = LanguageLoader("opspilot")
    descriptor = builtin_tools.build_builtin_monitor_tool(loader)

    assert descriptor["id"] == builtin_tools.BUILTIN_MONITOR_TOOL_ID
    assert descriptor["name"] == "monitor"
    assert descriptor["is_build_in"] is True
    assert descriptor["params"]["url"] == "langchain:monitor"
    # CONSTRUCTOR_PARAMS 不应作为子工具泄漏
    sub_names = {t["name"] for t in descriptor["tools"]}
    assert "CONSTRUCTOR_PARAMS" not in sub_names
    assert "monitor_list_objects" in sub_names


def test_builtin_monitor_runtime_tool_passes_param_prompt():
    """运行期描述符须透传 tool_kwargs 到 extra_param_prompt，并默认关闭鉴权。"""
    from apps.opspilot.services import builtin_tools

    runtime = builtin_tools.build_builtin_monitor_runtime_tool({"team_id": "12"})
    assert runtime["name"] == "monitor"
    assert runtime["url"] == "langchain:monitor"
    assert runtime["enable_auth"] is False
    assert runtime["extra_param_prompt"] == {"team_id": "12"}

    # None 时回退为空 dict
    runtime_none = builtin_tools.build_builtin_monitor_runtime_tool(None)
    assert runtime_none["extra_param_prompt"] == {}
