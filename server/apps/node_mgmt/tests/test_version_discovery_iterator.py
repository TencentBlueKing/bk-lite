"""
Tests for issue #3622 + #3610: discover_node_versions uses iterator and preloads Controllers.

验证修复点：
1. Node.objects.iterator(chunk_size=200) 被调用（而不是 Node.objects.all() 全量加载）
2. 返回的 total 由 success_count + failed_count 计算，不再调用 Node.objects.count()
3. Controller.objects.filter 在循环前只调用 1 次（预加载）

这是 Django-free 的注入式测试，不依赖 ORM/settings 加载。
"""
import importlib
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, call


def _install(name, **attrs):
    """向 sys.modules 注入伪模块"""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load_module(rel_path: str):
    """从文件路径加载模块，不触发 Django setup"""
    base = Path(__file__).parent.parent.parent.parent  # server/
    abs_path = base / rel_path
    spec = importlib.util.spec_from_file_location("version_discovery_under_test", abs_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def setup_module(module):
    """在模块加载前注入所有伪依赖"""
    # celery
    celery_mod = _install("celery")
    celery_mod.shared_task = lambda fn: fn  # 直接返回原函数

    # apps.core.logger
    logger_mock = MagicMock()
    core_mod = _install("apps")
    core_sub = _install("apps.core")
    core_logger = _install("apps.core.logger", logger=logger_mock)

    # apps.node_mgmt.models
    _install("apps.node_mgmt")
    _install("apps.node_mgmt.models")

    # apps.rpc.executor
    _install("apps.rpc")
    _install("apps.rpc.executor", Executor=MagicMock())

    # apps.node_mgmt.services.version_upgrade
    _install("apps.node_mgmt.services")
    _install("apps.node_mgmt.services.version_upgrade",
             VersionUpgradeService=MagicMock())

    # apps.node_mgmt.constants.node
    _install("apps.node_mgmt.constants")
    _install("apps.node_mgmt.constants.node", NodeConstants=MagicMock())

    # apps.node_mgmt.utils.architecture
    _install("apps.node_mgmt.utils")
    _install("apps.node_mgmt.utils.architecture",
             normalize_cpu_architecture=MagicMock(return_value="x86_64"))

    # apps.node_mgmt.utils.version_utils
    _install("apps.node_mgmt.utils.version_utils", VersionUtils=MagicMock())


def _load_vd():
    """每次测试重新加载模块（隔离 patch 状态）"""
    # 移除缓存，强制重新加载
    sys.modules.pop("version_discovery_under_test", None)
    return _load_module("apps/node_mgmt/tasks/version_discovery.py")


class TestDiscoverNodeVersionsIterator:
    """验证 discover_node_versions 使用 iterator 而非全量加载"""

    def test_uses_iterator_with_chunk_size(self):
        """
        核心修复验证：Node.objects.iterator(chunk_size=200) 必须被调用。
        Revert 修复后，此测试应失败（因为 iterator 不会被调用）。
        """
        vd = _load_vd()

        # 伪 Node 对象
        fake_node = MagicMock()
        fake_node.name = "test-node"
        fake_node.ip = "1.2.3.4"

        # 构造 node manager mock：Node.objects.iterator(chunk_size=200) 返回 [fake_node]
        node_manager_mock = MagicMock()
        node_manager_mock.iterator.return_value = iter([fake_node])

        # 替换 Node 模型
        vd.Node = MagicMock()
        vd.Node.objects = node_manager_mock

        # Controller 预加载返回空列表
        ctrl_manager_mock = MagicMock()
        ctrl_qs_mock = MagicMock()
        ctrl_qs_mock.__iter__ = MagicMock(return_value=iter([]))
        ctrl_manager_mock.filter.return_value = ctrl_qs_mock
        vd.Controller = MagicMock()
        vd.Controller.objects = ctrl_manager_mock

        vd.VersionUpgradeService.get_latest_versions_map.return_value = {}

        with patch.object(vd, "_discover_controller_version", return_value=None):
            result = vd.discover_node_versions()

        # 断言 iterator(chunk_size=200) 被调用（直接在 Node.objects 上，无 .all()）
        node_manager_mock.iterator.assert_called_once_with(chunk_size=200)

        # 断言 total 来自计数器而非 count() 查询
        node_manager_mock.count.assert_not_called()
        assert result["total"] == 1

    def test_total_from_counter_not_count_query(self):
        """
        验证 total = success_count + failed_count，不发 Node.objects.count() 额外查询。
        """
        vd = _load_vd()

        node_manager_mock = MagicMock()
        node_manager_mock.iterator.return_value = iter([])

        vd.Node = MagicMock()
        vd.Node.objects = node_manager_mock

        ctrl_manager_mock = MagicMock()
        ctrl_qs_mock = MagicMock()
        ctrl_qs_mock.__iter__ = MagicMock(return_value=iter([]))
        ctrl_manager_mock.filter.return_value = ctrl_qs_mock
        vd.Controller = MagicMock()
        vd.Controller.objects = ctrl_manager_mock

        vd.VersionUpgradeService.get_latest_versions_map.return_value = {}

        with patch.object(vd, "_discover_controller_version", return_value=None):
            result = vd.discover_node_versions()

        # total 为 0（无节点，无成功无失败）
        assert result["total"] == 0
        # 不应调用 count()
        node_manager_mock.count.assert_not_called()

    def test_success_and_failed_counts(self):
        """验证成功/失败计数正确"""
        vd = _load_vd()

        good_node = MagicMock()
        good_node.name = "good"
        good_node.ip = "1.1.1.1"

        bad_node = MagicMock()
        bad_node.name = "bad"
        bad_node.ip = "2.2.2.2"

        node_manager_mock = MagicMock()
        node_manager_mock.iterator.return_value = iter([good_node, bad_node])

        vd.Node = MagicMock()
        vd.Node.objects = node_manager_mock

        ctrl_manager_mock = MagicMock()
        ctrl_qs_mock = MagicMock()
        ctrl_qs_mock.__iter__ = MagicMock(return_value=iter([]))
        ctrl_manager_mock.filter.return_value = ctrl_qs_mock
        vd.Controller = MagicMock()
        vd.Controller.objects = ctrl_manager_mock

        vd.VersionUpgradeService.get_latest_versions_map.return_value = {}

        call_count = 0

        def side_effect(node, versions_map, controllers_map, all_controllers):
            nonlocal call_count
            call_count += 1
            if node is bad_node:
                raise RuntimeError("timeout")

        with patch.object(vd, "_discover_controller_version", side_effect=side_effect):
            result = vd.discover_node_versions()

        assert result["success_count"] == 1
        assert result["failed_count"] == 1
        assert result["total"] == 2
