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


def test_monitor_tools_loader_metadata_includes_monitor():
    from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader

    metadata = ToolsLoader.get_all_tools_metadata()

    monitor_item = next(item for item in metadata if item["name"] == "monitor")
    assert monitor_item["constructor"].endswith("tools.monitor")
    assert any(tool["name"] == "monitor_list_objects" for tool in monitor_item["tools"])
