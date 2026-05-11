import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from apps.job_mgmt.constants import ExecutionStatus, OSType
from apps.job_mgmt.models import JobExecution
from apps.job_mgmt.nats_api import ansible_task_callback
from apps.job_mgmt.services.file_distribution_runner import FileDistributionRunner
from apps.job_mgmt.services.script_execution_runner import ScriptExecutionRunner
from apps.rpc.ansible import AnsibleExecutor
from apps.system_mgmt import nats_api
from apps.system_mgmt.models import User
from apps.system_mgmt.nats_api import get_all_users, get_authorized_groups_scoped

logger = logging.getLogger(__name__)


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_target_view(monkeypatch):
    class AuthViewSet:
        pass

    class Response:
        def __init__(self, data, status=None):
            self.data = data
            self.status_code = status

    class BaseAppException(Exception):
        pass

    def action(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def has_permission(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    class _TargetManager:
        @staticmethod
        def all():
            return []

    class _Target:
        objects = _TargetManager()

    _install_module(monkeypatch, "rest_framework", status=types.SimpleNamespace(HTTP_400_BAD_REQUEST=400, HTTP_500_INTERNAL_SERVER_ERROR=500))
    _install_module(monkeypatch, "rest_framework.decorators", action=action)
    _install_module(monkeypatch, "rest_framework.response", Response=Response)
    _install_module(monkeypatch, "apps.core.decorators.api_permission", HasPermission=has_permission)
    _install_module(monkeypatch, "apps.core.exceptions.base_app_exception", BaseAppException=BaseAppException)
    _install_module(monkeypatch, "apps.core.logger", job_logger=types.SimpleNamespace(exception=lambda *args, **kwargs: None))
    _install_module(monkeypatch, "apps.core.utils.viewset_utils", AuthViewSet=AuthViewSet)
    _install_module(monkeypatch, "apps.job_mgmt.constants", OSType=object(), SSHCredentialType=object())
    _install_module(monkeypatch, "apps.job_mgmt.filters.target", TargetFilter=object)
    _install_module(monkeypatch, "apps.job_mgmt.models", Target=_Target)
    _install_module(
        monkeypatch,
        "apps.job_mgmt.serializers.target",
        TargetBatchDeleteSerializer=object,
        TargetSerializer=object,
        TargetTestConnectionSerializer=object,
    )
    _install_module(monkeypatch, "apps.node_mgmt.models", CloudRegion=object)
    _install_module(monkeypatch, "apps.rpc.executor", Executor=object)
    _install_module(monkeypatch, "apps.rpc.node_mgmt", NodeMgmt=object)
    _install_module(monkeypatch, "apps.rpc.system_mgmt", SystemMgmt=object)

    return _load_module(
        "job_target_view_test_module",
        Path(__file__).resolve().parents[2] / "job_mgmt" / "views" / "target.py",
    )


def create_test_users():
    """创建测试用户数据"""
    test_users = [
        {
            "username": "test_user1",
            "display_name": "测试用户1",
            "email": "test1@example.com",
            "password": make_password("password123"),
            "locale": "zh-Hans",
        },
        {
            "username": "test_user2",
            "display_name": "测试用户2",
            "email": "test2@example.com",
            "password": make_password("password123"),
            "locale": "en-US",
        },
    ]

    # 创建测试用户并返回创建的用户列表
    created_users = []
    for user_data in test_users:
        user = User.objects.create(**user_data)
        created_users.append(user)

    return created_users


@pytest.mark.django_db
def test_get_all_users():
    # 初始化测试用户数据
    create_test_users()

    # 调用被测函数
    result = get_all_users()
    logger.info(result)

    # 验证结果
    assert result["result"] is True
    assert len(result["data"]) >= 2  # 至少包含我们创建的两个用户

    # 验证返回的用户数据包含我们创建的用户
    usernames = [user["username"] for user in result["data"]]
    assert "test_user1" in usernames
    assert "test_user2" in usernames


def test_get_authorized_groups_scoped_rejects_forged_current_team(monkeypatch):
    user = types.SimpleNamespace(username="scope-user", domain="domain.com", group_list=[1])

    class _UserQuerySet:
        @staticmethod
        def first():
            return user

    class _UserManager:
        @staticmethod
        def filter(**kwargs):
            return _UserQuerySet()

    monkeypatch.setattr(nats_api.User, "objects", _UserManager())

    result = get_authorized_groups_scoped(
        {
            "username": "scope-user",
            "domain": "domain.com",
            "current_team": 2,
            "is_superuser": False,
        },
        include_children=True,
    )

    assert result == {"result": True, "data": []}


def test_get_authorized_groups_scoped_keeps_include_children(monkeypatch):
    user = types.SimpleNamespace(username="scope-children-user", domain="domain.com", group_list=[1])

    class _UserQuerySet:
        @staticmethod
        def first():
            return user

    class _UserManager:
        @staticmethod
        def filter(**kwargs):
            return _UserQuerySet()

    monkeypatch.setattr(nats_api.User, "objects", _UserManager())

    captured = {}

    def fake_get_user_authorized_child_groups(user_group_list, target_group_id, include_children=False):
        captured["user_group_list"] = user_group_list
        captured["target_group_id"] = target_group_id
        captured["include_children"] = include_children
        return [1, 11]

    monkeypatch.setattr(nats_api.GroupUtils, "get_user_authorized_child_groups", fake_get_user_authorized_child_groups)

    result = get_authorized_groups_scoped(
        {
            "username": "scope-children-user",
            "domain": "domain.com",
            "current_team": 1,
            "is_superuser": False,
        },
        include_children=True,
    )

    assert result == {"result": True, "data": [1, 11]}
    assert captured == {
        "user_group_list": [1],
        "target_group_id": 1,
        "include_children": True,
    }


def test_get_authorized_groups_scoped_rejects_invalid_current_team(monkeypatch):
    user = types.SimpleNamespace(username="scope-invalid-user", domain="domain.com", group_list=[1])

    class _UserQuerySet:
        @staticmethod
        def first():
            return user

    class _UserManager:
        @staticmethod
        def filter(**kwargs):
            return _UserQuerySet()

    monkeypatch.setattr(nats_api.User, "objects", _UserManager())

    result = get_authorized_groups_scoped(
        {
            "username": "scope-invalid-user",
            "domain": "domain.com",
            "current_team": "abc",
            "is_superuser": False,
        },
        include_children=False,
    )

    assert result == {"result": True, "data": []}


def test_target_query_nodes_propagates_authorized_scope_and_include_children(monkeypatch):
    captured = {}

    class NodeMgmt:
        def node_list(self, payload):
            captured["payload"] = payload
            return {"count": 0, "nodes": []}

    class SystemMgmt:
        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            captured["actor_context"] = actor_context
            captured["include_children"] = include_children
            return {"result": True, "data": [3, 5]}

    class CloudRegionQuerySetStub:
        def values(self, *args):
            return []

    class CloudRegionManagerStub:
        def all(self):
            return CloudRegionQuerySetStub()

    class CloudRegionStub:
        objects = CloudRegionManagerStub()

    module = _load_target_view(monkeypatch)
    module.NodeMgmt = NodeMgmt
    module.SystemMgmt = SystemMgmt
    module.CloudRegion = CloudRegionStub

    request = types.SimpleNamespace(
        query_params={"page": "1", "page_size": "20"},
        COOKIES={"current_team": "3", "include_children": "1"},
        user=types.SimpleNamespace(
            username="job-user",
            domain="domain.com",
            is_superuser=False,
        ),
    )

    response = module.TargetViewSet().query_nodes(request)

    assert response.data["result"] is True
    assert captured["actor_context"] == {
        "username": "job-user",
        "domain": "domain.com",
        "current_team": 3,
        "include_children": True,
        "is_superuser": False,
    }
    assert captured["include_children"] is True
    assert captured["payload"]["organization_ids"] == [3, 5]
    assert captured["payload"]["permission_data"] == {
        "username": "job-user",
        "domain": "domain.com",
        "current_team": 3,
        "include_children": True,
    }


def test_target_query_nodes_rejects_invalid_current_team_cookie(monkeypatch):
    module = _load_target_view(monkeypatch)

    request = types.SimpleNamespace(
        query_params={"page": "1", "page_size": "20"},
        COOKIES={"current_team": "abc"},
        user=types.SimpleNamespace(
            username="job-user",
            domain="domain.com",
            is_superuser=False,
        ),
    )

    response = module.TargetViewSet().query_nodes(request)

    assert response.status_code == 400
    assert response.data == {"result": False, "message": "current_team 参数非法"}


def parse_data(data):
    items = data["data"].get("items", [])
    processed_items = []  # 用于暂存所有处理后的原始数据与计数，便于排序

    for item in items:
        bk_biz_name = item.get("bk_biz_name", "未知业务")
        active_status = item.get("active_status_count", {})

        # 告警相关数量
        warning_count = active_status.get("warning", 0)
        fatal_count = active_status.get("fatal", 0)
        remain_count = active_status.get("remain", 0)

        # 活动告警总数量 = warning + fatal
        active_alert_count = warning_count + fatal_count
        # 决定状态
        if fatal_count > 0:
            status = "danger"
        elif warning_count > 0 or remain_count > 0:
            status = "warned"
        else:
            status = "normal"

        brief = str(active_alert_count)

        # 暂时保存所有必要信息，用于后续排序
        processed_items.append(
            {
                "bk_biz_name": bk_biz_name,
                "fatal_count": fatal_count,
                "warning_count": warning_count,
                "remain_count": remain_count,
                "status": status,
                "brief": brief,
            }
        )

    # 排序：首先按 fatal_count 降序，然后 warning_count 降序，然后 remain_count 降序
    processed_items_sorted = sorted(processed_items, key=lambda x: (-x["fatal_count"], -x["warning_count"], -x["remain_count"]))

    # 构造最终返回的列表
    return_data = []
    for pitem in processed_items_sorted:
        transformed_item = {
            "status": pitem["status"],
            "name": pitem["bk_biz_name"],
            "brief": pitem["brief"],
            "other_url": False,
        }
        return_data.append(transformed_item)

    return True, return_data


@pytest.mark.django_db
def test_ansible_task_callback_records_ansible_failure_payload():
    execution = JobExecution.objects.create(
        name="ansible failure callback",
        job_type="script",
        status=ExecutionStatus.RUNNING,
        target_list=[{"target_id": 1, "name": "host-1", "ip": "10.10.41.149"}],
        started_at=timezone.now(),
    )
    payload = {
        "task_id": str(execution.id),
        "task_type": "adhoc",
        "status": "failed",
        "success": False,
        "result": [
            {
                "host": "10.10.41.149",
                "status": "failed",
                "raw_status": "FAILED",
                "stdout": "",
                "stderr": "to use the 'ssh' connection type with passwords or pkcs11_provider, you must install the sshpass program",
                "exit_code": 2,
                "error_message": "to use the 'ssh' connection type with passwords or pkcs11_provider, you must install the sshpass program",
            }
        ],
        "error": "ansible adhoc failed with exit code 2",
        "started_at": "2026-03-27T09:50:10.546905+00:00",
        "finished_at": "2026-03-27T09:50:11.536357+00:00",
    }

    result = ansible_task_callback(payload)

    execution.refresh_from_db()

    assert result == {"success": True, "message": "回调处理成功"}
    assert execution.status == ExecutionStatus.FAILED
    assert execution.success_count == 0
    assert execution.failed_count == 1
    assert len(execution.execution_results) == 1
    assert execution.execution_results[0]["status"] == ExecutionStatus.FAILED
    assert execution.execution_results[0]["stdout"] == ""
    assert execution.execution_results[0]["stderr"] == payload["result"][0]["stderr"]
    assert execution.execution_results[0]["error_message"] == payload["result"][0]["error_message"]
    assert execution.execution_results[0]["exit_code"] == 2


@pytest.mark.django_db
def test_ansible_task_callback_consumes_per_host_result_array():
    execution = JobExecution.objects.create(
        name="ansible host array callback",
        job_type="script",
        status=ExecutionStatus.RUNNING,
        target_list=[
            {"target_id": 1, "name": "host-1", "ip": "10.10.41.149"},
            {"target_id": 2, "name": "host-2", "ip": "10.10.41.150"},
        ],
        started_at=timezone.now(),
    )
    payload = {
        "task_id": str(execution.id),
        "task_type": "adhoc",
        "status": "failed",
        "success": False,
        "result": [
            {
                "host": "10.10.41.149",
                "status": "success",
                "raw_status": "CHANGED",
                "stdout": "ok-149",
                "stderr": "",
                "exit_code": 0,
                "error_message": "",
            },
            {
                "host": "10.10.41.150",
                "status": "failed",
                "raw_status": "FAILED",
                "stdout": "",
                "stderr": "boom-150",
                "exit_code": 2,
                "error_message": "boom-150",
            },
        ],
        "error": "ansible adhoc failed with exit code 2",
        "started_at": "2026-03-27T09:50:10.546905+00:00",
        "finished_at": "2026-03-27T09:50:11.536357+00:00",
    }

    result = ansible_task_callback(payload)

    execution.refresh_from_db()

    assert result == {"success": True, "message": "回调处理成功"}
    assert execution.status == ExecutionStatus.FAILED
    assert execution.success_count == 1
    assert execution.failed_count == 1
    assert len(execution.execution_results) == 2
    assert execution.execution_results[0]["ip"] == "10.10.41.149"
    assert execution.execution_results[0]["status"] == ExecutionStatus.SUCCESS
    assert execution.execution_results[0]["stdout"] == "ok-149"
    assert execution.execution_results[0]["stderr"] == ""
    assert execution.execution_results[0]["exit_code"] == 0
    assert execution.execution_results[1]["ip"] == "10.10.41.150"
    assert execution.execution_results[1]["status"] == ExecutionStatus.FAILED
    assert execution.execution_results[1]["stdout"] == ""
    assert execution.execution_results[1]["stderr"] == "boom-150"
    assert execution.execution_results[1]["error_message"] == "boom-150"
    assert execution.execution_results[1]["exit_code"] == 2


def test_file_distribution_normalizes_windows_target_path_before_remote_download(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        FileDistributionRunner,
        "get_ssh_credentials",
        classmethod(
            lambda cls, target_id: {
                "host": "10.10.41.149",
                "username": "Administrator",
                "password": "secret",
                "private_key": None,
                "port": 22,
                "node_id": "node-1",
            }
        ),
    )
    monkeypatch.setattr(
        "apps.job_mgmt.services.file_distribution_runner.Target.objects.filter",
        lambda **kwargs: type(
            "QuerySet",
            (),
            {
                "first": staticmethod(
                    lambda: type(
                        "TargetObj",
                        (),
                        {
                            "driver": "executor",
                            "cloud_region_id": None,
                            "os_type": OSType.WINDOWS,
                            "ip": "10.10.41.149",
                            "winrm_user": "Administrator",
                            "winrm_password": "encrypted-winrm-password",
                            "winrm_port": 5986,
                            "node_id": "node-1",
                        },
                    )()
                )
            },
        )(),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "decrypt_password",
        staticmethod(lambda value: f"decrypted::{value}" if value else ""),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "download_to_remote",
        staticmethod(
            lambda instance_id, file_item, target_path, ssh_creds, timeout, overwrite: captured.update(
                {
                    "instance_id": instance_id,
                    "file_item": file_item,
                    "target_path": target_path,
                    "ssh_creds": ssh_creds,
                    "timeout": timeout,
                    "overwrite": overwrite,
                }
            )
            or {"success": True}
        ),
    )

    runner = FileDistributionRunner(execution_id=1)
    file_item = {"name": "config.ini", "file_key": "abc"}

    runner.download_to_manual_target(
        file_item=file_item,
        target_id=1,
        target_path=r"C:\temp\nested\config.ini",
        timeout=60,
        overwrite=True,
    )

    assert captured["target_path"] == "C:/temp/nested/config.ini"
    assert captured["ssh_creds"]["username"] == "Administrator"
    assert captured["ssh_creds"]["password"] == "decrypted::encrypted-winrm-password"
    assert captured["ssh_creds"]["port"] == 5986


def test_file_distribution_uses_winrm_password_for_windows_manual_target(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        FileDistributionRunner,
        "get_ssh_credentials",
        classmethod(
            lambda cls, target_id: {
                "host": "10.10.41.149",
                "username": "",
                "password": "",
                "private_key": None,
                "port": 22,
                "node_id": "node-1",
            }
        ),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "decrypt_password",
        staticmethod(lambda value: f"decrypted::{value}" if value else ""),
    )
    monkeypatch.setattr(
        "apps.job_mgmt.services.file_distribution_runner.Target.objects.filter",
        lambda **kwargs: type(
            "QuerySet",
            (),
            {
                "first": staticmethod(
                    lambda: type(
                        "TargetObj",
                        (),
                        {
                            "driver": "executor",
                            "cloud_region_id": None,
                            "os_type": OSType.WINDOWS,
                            "ip": "10.10.41.149",
                            "winrm_user": "Administrator",
                            "winrm_password": "encrypted-winrm-password",
                            "winrm_port": 5986,
                            "node_id": "node-1",
                        },
                    )()
                )
            },
        )(),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "download_to_remote",
        staticmethod(
            lambda instance_id, file_item, target_path, ssh_creds, timeout, overwrite: captured.update(
                {
                    "instance_id": instance_id,
                    "file_item": file_item,
                    "target_path": target_path,
                    "ssh_creds": ssh_creds,
                    "timeout": timeout,
                    "overwrite": overwrite,
                }
            )
            or {"success": True}
        ),
    )

    runner = FileDistributionRunner(execution_id=1)
    file_item = {"name": "vc密码.txt", "file_key": "abc"}

    runner.download_to_manual_target(
        file_item=file_item,
        target_id=1,
        target_path=r"C:\temp\vc密码.txt",
        timeout=60,
        overwrite=True,
    )

    assert captured["ssh_creds"]["host"] == "10.10.41.149"
    assert captured["ssh_creds"]["username"] == "Administrator"
    assert captured["ssh_creds"]["password"] == "decrypted::encrypted-winrm-password"
    assert captured["ssh_creds"]["private_key"] is None
    assert captured["ssh_creds"]["port"] == 5986


@pytest.mark.django_db
def test_manual_windows_script_execution_routes_to_ansible(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        ScriptExecutionRunner,
        "_should_use_ansible",
        staticmethod(lambda target_source, target_list: True),
    )
    monkeypatch.setattr(
        ScriptExecutionRunner,
        "_execute_script_via_ansible",
        classmethod(
            lambda cls, execution, target_list, script_content, script_type: captured.update(
                {
                    "called": True,
                    "target_list": target_list,
                    "script_content": script_content,
                    "script_type": script_type,
                }
            )
        ),
    )
    monkeypatch.setattr(
        ScriptExecutionRunner,
        "_run_via_sidecar",
        lambda self, execution, target_list, script_content: (_ for _ in ()).throw(AssertionError("sidecar should not be used")),
    )
    monkeypatch.setattr(
        ScriptExecutionRunner,
        "_handle_dangerous_command",
        lambda self, execution, target_list: False,
    )

    execution = JobExecution.objects.create(
        name="windows script ansible route",
        job_type="script",
        status=ExecutionStatus.PENDING,
        target_source="manual",
        target_list=[{"target_id": 1, "name": "win-host", "ip": "10.10.41.149"}],
        script_type="powershell",
        script_content="Write-Host 'hello'",
        timeout=120,
    )

    runner = ScriptExecutionRunner(execution.id)
    runner.run()

    assert captured["called"] is True
    assert captured["target_list"] == execution.target_list
    assert captured["script_type"] == "powershell"
    assert captured["script_content"] == "Write-Host 'hello'"


def test_file_distribution_routes_manual_windows_ansible_target_to_ansible_executor(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "apps.job_mgmt.services.file_distribution_runner.Target.objects.filter",
        lambda **kwargs: type(
            "QuerySet",
            (),
            {
                "first": staticmethod(
                    lambda: type(
                        "TargetObj",
                        (),
                        {
                            "id": 1,
                            "ip": "10.10.41.149",
                            "os_type": OSType.WINDOWS,
                            "driver": "ansible",
                            "cloud_region_id": 11,
                            "winrm_user": "Administrator",
                            "winrm_password": "encrypted-winrm-password",
                            "winrm_port": 5986,
                            "winrm_scheme": "https",
                            "winrm_transport": "ntlm",
                            "winrm_cert_validation": False,
                        },
                    )()
                )
            },
        )(),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "decrypt_password",
        staticmethod(lambda value: f"decrypted::{value}" if value else ""),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "_get_ansible_node",
        staticmethod(lambda cloud_region_id: "ansible-node-1"),
    )
    monkeypatch.setattr(
        AnsibleExecutor,
        "playbook",
        lambda self, **kwargs: captured.update({"playbook_kwargs": kwargs})
        or {"accepted": True, "status": "queued", "task_id": "task-123", "duplicate": False},
    )
    monkeypatch.setattr(
        AnsibleExecutor,
        "task_query",
        lambda self, task_id, timeout=10: {
            "task_id": task_id,
            "status": "success",
            "payload": {},
            "callback": {},
            "result": {
                "task_id": task_id,
                "task_type": "playbook",
                "status": "success",
                "success": True,
                "result": [
                    {
                        "host": "10.10.41.149",
                        "status": "success",
                        "raw_status": "CHANGED",
                        "stdout": "copied",
                        "stderr": "",
                        "exit_code": 0,
                        "error_message": "",
                    }
                ],
                "error": "",
            },
            "created_at": "2026-04-03T07:35:53.859291+00:00",
            "updated_at": "2026-04-03T07:35:53.880230+00:00",
        },
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "download_to_remote",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scp path should not be used"))),
    )

    runner = FileDistributionRunner(execution_id=42)
    result = runner.download_to_manual_target(
        file_item={"name": "config.ini", "file_key": "abc"},
        target_id=1,
        target_path=r"C:\deploy",
        timeout=60,
        overwrite=True,
    )

    assert captured["playbook_kwargs"]["files"] == [{"name": "config.ini", "file_key": "abc"}]
    assert captured["playbook_kwargs"]["file_distribution"]["target_path"] == "C:/deploy"
    assert captured["playbook_kwargs"]["host_credentials"][0]["connection"] == "winrm"
    assert result["success"] is True
    assert result["error"] == ""
    assert result["result"][0]["host"] == "10.10.41.149"


def test_ansible_playbook_allows_file_distribution_without_playbook():
    captured = {}

    class DummyClient:
        def run(self, instance_id, request_data, _timeout=None):
            captured["instance_id"] = instance_id
            captured["request_data"] = request_data
            captured["timeout"] = _timeout
            return {"success": True, "result": {"accepted": True}}

    executor = AnsibleExecutor("ansible-node-1")
    executor.playbook_client = DummyClient()

    result = executor.playbook(
        host_credentials=[{"host": "10.0.0.1", "user": "Administrator", "password": "secret", "connection": "winrm"}],
        files=[{"name": "channel_add.txt", "file_key": "file-key-1"}],
        file_distribution={"bucket_name": "test-bucket", "target_path": "C:/deploy", "overwrite": True},
        task_id="task-1",
        timeout=30,
    )

    assert result == {"success": True, "result": {"accepted": True}}
    assert captured["instance_id"] == "ansible-node-1"
    assert captured["timeout"] == 30
    assert captured["request_data"]["playbook_path"] == ""
    assert captured["request_data"]["playbook_content"] is None
    assert captured["request_data"]["files"] == [{"name": "channel_add.txt", "file_key": "file-key-1"}]
    assert captured["request_data"]["file_distribution"] == {"bucket_name": "test-bucket", "target_path": "C:/deploy", "overwrite": True}


def test_file_distribution_polls_until_ansible_task_finishes(monkeypatch):
    monkeypatch.setattr(
        "apps.job_mgmt.services.file_distribution_runner.Target.objects.filter",
        lambda **kwargs: type(
            "QuerySet",
            (),
            {
                "first": staticmethod(
                    lambda: type(
                        "TargetObj",
                        (),
                        {
                            "id": 1,
                            "ip": "10.10.41.149",
                            "os_type": OSType.WINDOWS,
                            "driver": "ansible",
                            "cloud_region_id": 11,
                            "winrm_user": "Administrator",
                            "winrm_password": "encrypted-winrm-password",
                            "winrm_port": 5986,
                            "winrm_scheme": "https",
                            "winrm_transport": "ntlm",
                            "winrm_cert_validation": False,
                        },
                    )()
                )
            },
        )(),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "decrypt_password",
        staticmethod(lambda value: f"decrypted::{value}" if value else ""),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "_get_ansible_node",
        staticmethod(lambda cloud_region_id: "ansible-node-1"),
    )
    monkeypatch.setattr(
        AnsibleExecutor,
        "playbook",
        lambda self, **kwargs: {"accepted": True, "status": "queued", "task_id": "task-running", "duplicate": False},
    )
    query_results = iter(
        [
            {
                "task_id": "task-running",
                "status": "running",
                "payload": {},
                "callback": {},
                "result": {"started_at": "2026-04-07T10:44:08.910000+00:00"},
            },
            {
                "task_id": "task-running",
                "status": "success",
                "payload": {},
                "callback": {},
                "result": {
                    "task_id": "task-running",
                    "task_type": "playbook",
                    "status": "success",
                    "success": True,
                    "result": [
                        {
                            "host": "10.10.41.149",
                            "status": "success",
                            "raw_status": "CHANGED",
                            "stdout": "copied",
                            "stderr": "",
                            "exit_code": 0,
                            "error_message": "",
                        }
                    ],
                    "error": "",
                },
            },
        ]
    )
    monkeypatch.setattr(
        AnsibleExecutor,
        "task_query",
        lambda self, task_id, timeout=10: next(query_results),
    )
    monkeypatch.setattr("apps.job_mgmt.services.file_distribution_runner.time.sleep", lambda _: None)

    runner = FileDistributionRunner(execution_id=42)
    result = runner.download_to_manual_target(
        file_item={"name": "config.ini", "file_key": "abc"},
        target_id=1,
        target_path=r"C:\deploy",
        timeout=60,
        overwrite=True,
    )

    assert result["success"] is True
    assert result["error"] == ""
    assert result["result"][0]["host"] == "10.10.41.149"


def test_file_distribution_raises_when_ansible_task_query_stays_running(monkeypatch):
    monkeypatch.setattr(
        "apps.job_mgmt.services.file_distribution_runner.Target.objects.filter",
        lambda **kwargs: type(
            "QuerySet",
            (),
            {
                "first": staticmethod(
                    lambda: type(
                        "TargetObj",
                        (),
                        {
                            "id": 1,
                            "ip": "10.10.41.149",
                            "os_type": OSType.WINDOWS,
                            "driver": "ansible",
                            "cloud_region_id": 11,
                            "winrm_user": "Administrator",
                            "winrm_password": "encrypted-winrm-password",
                            "winrm_port": 5986,
                            "winrm_scheme": "https",
                            "winrm_transport": "ntlm",
                            "winrm_cert_validation": False,
                        },
                    )()
                )
            },
        )(),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "decrypt_password",
        staticmethod(lambda value: f"decrypted::{value}" if value else ""),
    )
    monkeypatch.setattr(
        FileDistributionRunner,
        "_get_ansible_node",
        staticmethod(lambda cloud_region_id: "ansible-node-1"),
    )
    monkeypatch.setattr(
        AnsibleExecutor,
        "playbook",
        lambda self, **kwargs: {"accepted": True, "status": "queued", "task_id": "task-running", "duplicate": False},
    )
    monkeypatch.setattr(
        AnsibleExecutor,
        "task_query",
        lambda self, task_id, timeout=10: {
            "task_id": task_id,
            "status": "running",
            "payload": {},
            "callback": {},
            "result": {"started_at": "2026-04-07T10:44:08.910000+00:00"},
        },
    )
    monkeypatch.setattr("apps.job_mgmt.services.file_distribution_runner.time.sleep", lambda _: None)

    runner = FileDistributionRunner(execution_id=42)

    with pytest.raises(ValueError, match="Ansible 文件分发任务未完成: status=running"):
        runner.download_to_manual_target(
            file_item={"name": "config.ini", "file_key": "abc"},
            target_id=1,
            target_path=r"C:\deploy",
            timeout=2,
            overwrite=True,
        )
