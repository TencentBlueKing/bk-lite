"""
Tests for issue #3622: discover_node_versions uses iterator to avoid full-table OOM.

验证修复点：
1. Node.objects.all().iterator(chunk_size=500) 被调用（而不是 Node.objects.all() 全量加载）
2. 返回的 total 来自独立的 Node.objects.count()，而不是已遍历 queryset 的 .count()

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
        核心修复验证：Node.objects.all().iterator(chunk_size=500) 必须被调用。
        Revert 修复后，此测试应失败（因为 iterator 不会被调用）。
        """
        vd = _load_vd()

        # 伪 Node 对象
        fake_node = MagicMock()
        fake_node.name = "test-node"
        fake_node.ip = "1.2.3.4"

        # 构造可链式调用的 queryset mock：
        # Node.objects.all() 返回 qs_mock，qs_mock.iterator(chunk_size=500) 返回 [fake_node]
        qs_mock = MagicMock()
        qs_mock.iterator.return_value = iter([fake_node])

        node_manager_mock = MagicMock()
        node_manager_mock.all.return_value = qs_mock
        node_manager_mock.count.return_value = 1

        # 替换 Node 模型
        vd.Node = MagicMock()
        vd.Node.objects = node_manager_mock

        # 让 _discover_controller_version 不报错
        vd.VersionUpgradeService.get_latest_versions_map.return_value = {}

        with patch.object(vd, "_discover_controller_version", return_value=None):
            result = vd.discover_node_versions()

        # 断言 iterator(chunk_size=500) 被调用
        qs_mock.iterator.assert_called_once_with(chunk_size=500)

        # 断言返回值中 total 来自独立的 count()
        node_manager_mock.count.assert_called_once()
        assert result["total"] == 1

    def test_total_from_count_not_queryset(self):
        """
        验证 total 来自 Node.objects.count()，而非已遍历 queryset 的 .count()。
        避免全量遍历后再额外发出一条 COUNT SQL。
        """
        vd = _load_vd()

        qs_mock = MagicMock()
        qs_mock.iterator.return_value = iter([])

        node_manager_mock = MagicMock()
        node_manager_mock.all.return_value = qs_mock
        node_manager_mock.count.return_value = 42

        vd.Node = MagicMock()
        vd.Node.objects = node_manager_mock
        vd.VersionUpgradeService.get_latest_versions_map.return_value = {}

        with patch.object(vd, "_discover_controller_version", return_value=None):
            result = vd.discover_node_versions()

        assert result["total"] == 42
        # qs_mock.count 不应被调用（已废弃的旧写法）
        qs_mock.count.assert_not_called()

    def test_success_and_failed_counts(self):
        """验证成功/失败计数正确"""
        vd = _load_vd()

        good_node = MagicMock()
        good_node.name = "good"
        good_node.ip = "1.1.1.1"

        bad_node = MagicMock()
        bad_node.name = "bad"
        bad_node.ip = "2.2.2.2"

        qs_mock = MagicMock()
        qs_mock.iterator.return_value = iter([good_node, bad_node])

        node_manager_mock = MagicMock()
        node_manager_mock.all.return_value = qs_mock
        node_manager_mock.count.return_value = 2

        vd.Node = MagicMock()
        vd.Node.objects = node_manager_mock
        vd.VersionUpgradeService.get_latest_versions_map.return_value = {}

        call_count = 0

        def side_effect(node, versions_map):
            nonlocal call_count
            call_count += 1
            if node is bad_node:
                raise RuntimeError("timeout")

        with patch.object(vd, "_discover_controller_version", side_effect=side_effect):
            result = vd.discover_node_versions()

        assert result["success_count"] == 1
        assert result["failed_count"] == 1
        assert result["total"] == 2
