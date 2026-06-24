"""
Tests for issue #3611: process_node_data 应使用 filter(id__in=...) 而非 Collector.objects.all()

这些测试使用模块注入方式加载被测模块，无需完整 Django 环境即可运行。
验证原则：revert 修复代码后，所有测试均应失败。
"""
import sys
import types
from unittest.mock import MagicMock
import importlib.util
import pytest


def _install(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


@pytest.fixture(scope="module")
def node_service_module():
    """加载 node.py 并注入最小化伪依赖，返回模块对象。"""
    # 避免重复注入已有模块
    saved = {}
    inject_names = [
        "django", "django.db", "django.db.models", "django.utils", "django.utils.timezone",
        "apps.core.exceptions.base_app_exception",
        "apps.core.utils.permission_utils",
        "apps.core.logger",
        "apps.node_mgmt.constants.collector",
        "apps.node_mgmt.constants.controller",
        "apps.node_mgmt.constants.node",
        "apps.node_mgmt.models",
        "apps.node_mgmt.models.sidecar",
        "apps.node_mgmt.models.action",
        "apps.node_mgmt.tasks",
        "apps.node_mgmt.tasks.action_task",
        "apps.node_mgmt.serializers",
        "apps.node_mgmt.serializers.node",
        "apps.system_mgmt",
        "apps.system_mgmt.models",
        "apps.node_mgmt.services",
        "apps.node_mgmt.services.sidecar",
        "apps.rpc",
        "apps.rpc.system_mgmt",
        "apps.core.utils.safe_template",
    ]
    for n in inject_names:
        saved[n] = sys.modules.get(n)

    class FakeModel:
        pass

    _install("django")
    _install("django.db")
    _install("django.db.models", Model=FakeModel)
    _install("django.utils")
    _install("django.utils.timezone")
    _install("apps.core.exceptions.base_app_exception", BaseAppException=Exception)
    _install("apps.core.utils.permission_utils", get_permission_rules=lambda *a, **k: {})
    _install("apps.core.logger", node_logger=MagicMock())
    _install("apps.node_mgmt.constants.collector", CollectorConstants=MagicMock())
    _install("apps.node_mgmt.constants.controller", ControllerConstants=MagicMock())
    _install("apps.node_mgmt.constants.node", NodeConstants=MagicMock())

    fake_install_status = MagicMock()
    _install("apps.node_mgmt.models", NodeCollectorInstallStatus=fake_install_status)

    fake_collector_model = MagicMock()
    fake_collector_configuration_model = MagicMock()
    _install(
        "apps.node_mgmt.models.sidecar",
        Node=MagicMock(),
        Collector=fake_collector_model,
        CollectorConfiguration=fake_collector_configuration_model,
        Action=MagicMock(),
    )
    _install("apps.node_mgmt.models.action", CollectorActionTask=MagicMock(), CollectorActionTaskNode=MagicMock())
    _install("apps.node_mgmt.tasks")
    _install("apps.node_mgmt.tasks.action_task", timeout_collector_action_task=MagicMock(), ACTION_TASK_TIMEOUT_SECONDS=60)
    _install("apps.node_mgmt.serializers")
    _install("apps.node_mgmt.serializers.node", NodeSerializer=MagicMock())
    _install("apps.system_mgmt")
    _install("apps.system_mgmt.models", User=MagicMock())
    _install("apps.node_mgmt.services")
    _install("apps.node_mgmt.services.sidecar", Sidecar=MagicMock())
    _install("apps.rpc")
    _install("apps.rpc.system_mgmt", SystemMgmt=MagicMock())
    _install("apps.core.utils.safe_template", build_sandboxed_env=MagicMock())

    # 强制重新加载 node.py（规避 scope=module 下缓存问题）
    mod_name = "apps.node_mgmt.services.node_3611_test"
    spec = importlib.util.spec_from_file_location(
        mod_name,
        str(
            __import__("pathlib").Path(__file__).resolve().parent.parent
            / "services"
            / "node.py"
        ),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)

    # 把伪模型对象绑回模块，方便测试直接访问
    mod._fake_collector_model = fake_collector_model
    mod._fake_collector_configuration_model = fake_collector_configuration_model
    mod._fake_install_status = fake_install_status

    yield mod

    # 恢复被替换的模块
    for n, v in saved.items():
        if v is None:
            sys.modules.pop(n, None)
        else:
            sys.modules[n] = v


@pytest.fixture()
def setup_mocks(node_service_module):
    """每个测试前重置 mock 调用记录，返回 (NodeService, mocks dict)。"""
    ns = node_service_module
    ns._fake_collector_model.reset_mock()
    ns._fake_collector_configuration_model.reset_mock()
    ns._fake_install_status.reset_mock()

    mocks = {
        "Collector": ns._fake_collector_model,
        "CollectorConfiguration": ns._fake_collector_configuration_model,
        "InstallStatus": ns._fake_install_status,
    }
    return ns.NodeService, mocks


# ---------------------------------------------------------------------------
# 辅助：构建假 Collector 对象
# ---------------------------------------------------------------------------

def _mock_collector(cid, name):
    c = MagicMock()
    c.id = cid
    c.name = name
    return c


def _mock_config(cid, name):
    c = MagicMock()
    c.id = cid
    c.name = name
    return c


def _mock_install_obj(node_id, collector_id, status="success", result="ok"):
    obj = MagicMock()
    obj.node_id = node_id
    obj.collector_id = collector_id
    obj.status = status
    obj.result = result
    return obj


# ---------------------------------------------------------------------------
# 核心断言：Collector.objects.all() 不得被调用（这是修复的关键）
# ---------------------------------------------------------------------------

class TestCollectorQueryIsFiltered:
    def test_collector_all_is_never_called(self, setup_mocks):
        """回归测试：revert 修复后此测试应失败。"""
        NodeService, mocks = setup_mocks
        mocks["InstallStatus"].objects.filter.return_value = []
        mocks["Collector"].objects.filter.return_value = []
        mocks["CollectorConfiguration"].objects.filter.return_value = []

        node_data = [
            {
                "id": "n1",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "status": {
                    "collectors": [
                        {"collector_id": 1, "configuration_id": 10, "status": 0, "verbose_message": ""},
                    ]
                },
            }
        ]
        NodeService.process_node_data(node_data)

        assert not mocks["Collector"].objects.all.called, (
            "Collector.objects.all() was called — 修复未生效，存在全表扫描"
        )

    def test_collector_filter_called_with_correct_ids(self, setup_mocks):
        """filter(id__in=...) 必须包含 node status 中所有 collector_id。"""
        NodeService, mocks = setup_mocks
        mocks["InstallStatus"].objects.filter.return_value = []

        c1 = _mock_collector(1, "telegraf")
        c2 = _mock_collector(2, "vector")
        mocks["Collector"].objects.filter.return_value = [c1, c2]
        mocks["CollectorConfiguration"].objects.filter.return_value = []

        node_data = [
            {
                "id": "n1",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "status": {
                    "collectors": [
                        {"collector_id": 1, "configuration_id": 10, "status": 0, "verbose_message": ""},
                        {"collector_id": 2, "configuration_id": 20, "status": 0, "verbose_message": ""},
                    ]
                },
            }
        ]
        NodeService.process_node_data(node_data)

        assert mocks["Collector"].objects.filter.called
        call_kwargs = mocks["Collector"].objects.filter.call_args[1]
        assert set(call_kwargs["id__in"]) == {1, 2}

    def test_install_status_collector_ids_included_in_filter(self, setup_mocks):
        """NodeCollectorInstallStatus 中的 collector_id 也必须纳入 filter。"""
        NodeService, mocks = setup_mocks

        # 安装状态中有 collector_id=30，不在 node["status"]["collectors"] 里
        install_obj = _mock_install_obj("n1", 30)
        mocks["InstallStatus"].objects.filter.return_value = [install_obj]

        c30 = _mock_collector(30, "filebeat")
        mocks["Collector"].objects.filter.return_value = [c30]
        mocks["CollectorConfiguration"].objects.filter.return_value = []

        node_data = [
            {
                "id": "n1",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "status": {},  # no collectors key
            }
        ]
        NodeService.process_node_data(node_data)

        call_kwargs = mocks["Collector"].objects.filter.call_args[1]
        assert 30 in set(call_kwargs["id__in"]), (
            "collector_id=30（来自安装状态）未纳入 Collector.objects.filter"
        )

    def test_empty_node_list_does_not_call_collector_filter(self, setup_mocks):
        """空节点列表时，Collector.objects.filter 不应被调用（无 id__in）。"""
        NodeService, mocks = setup_mocks
        mocks["InstallStatus"].objects.filter.return_value = []

        result = NodeService.process_node_data([])

        assert result == []
        # filter 可能不被调用（id__in 为空集合时应短路），或被调用但参数为空集
        if mocks["Collector"].objects.filter.called:
            call_kwargs = mocks["Collector"].objects.filter.call_args[1]
            assert len(call_kwargs.get("id__in", [])) == 0


# ---------------------------------------------------------------------------
# 功能正确性：名称正确填充
# ---------------------------------------------------------------------------

class TestCollectorNameEnrichment:
    def test_collector_name_set_on_status_collectors(self, setup_mocks):
        NodeService, mocks = setup_mocks
        mocks["InstallStatus"].objects.filter.return_value = []
        c1 = _mock_collector(1, "telegraf")
        mocks["Collector"].objects.filter.return_value = [c1]
        cfg = _mock_config(10, "default-config")
        mocks["CollectorConfiguration"].objects.filter.return_value = [cfg]

        node_data = [
            {
                "id": "n1",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "status": {
                    "collectors": [
                        {"collector_id": 1, "configuration_id": 10, "status": 0, "verbose_message": ""},
                    ]
                },
            }
        ]
        result = NodeService.process_node_data(node_data)

        assert result[0]["status"]["collectors"][0]["collector_name"] == "telegraf"
        assert result[0]["status"]["collectors"][0]["configuration_name"] == "default-config"

    def test_install_status_collector_name_set(self, setup_mocks):
        NodeService, mocks = setup_mocks

        install_obj = _mock_install_obj("n1", 30, status="success")
        mocks["InstallStatus"].objects.filter.return_value = [install_obj]
        c30 = _mock_collector(30, "filebeat")
        mocks["Collector"].objects.filter.return_value = [c30]
        mocks["CollectorConfiguration"].objects.filter.return_value = []

        node_data = [
            {
                "id": "n1",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "status": {},
            }
        ]
        result = NodeService.process_node_data(node_data)

        install_entries = result[0]["status"]["collectors_install"]
        assert len(install_entries) == 1
        assert install_entries[0]["collector_name"] == "filebeat"

    def test_missing_collector_name_is_none(self, setup_mocks):
        """collector_id 不在查询结果中时，name 应为 None，不抛异常。"""
        NodeService, mocks = setup_mocks
        mocks["InstallStatus"].objects.filter.return_value = []
        mocks["Collector"].objects.filter.return_value = []  # 空结果
        mocks["CollectorConfiguration"].objects.filter.return_value = []

        node_data = [
            {
                "id": "n1",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "status": {
                    "collectors": [
                        {"collector_id": 99, "configuration_id": 999, "status": 0, "verbose_message": ""},
                    ]
                },
            }
        ]
        result = NodeService.process_node_data(node_data)
        assert result[0]["status"]["collectors"][0]["collector_name"] is None
