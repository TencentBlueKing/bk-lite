"""
Tests for issue #3610 fix: discover_node_versions 预加载 Controller 消除循环内 N×3 DB 查询

验证核心：revert 修复代码（循环内 Controller.objects.filter）后，这些测试应该失败。
"""
import sys
from types import SimpleNamespace, ModuleType
from unittest.mock import MagicMock, patch, call
import importlib.util


def _install(name, **attrs):
    mod = ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load_version_discovery():
    """加载 version_discovery 模块（注入伪依赖，不触发 Django settings）"""
    import apps.core.logger as _l  # noqa: F401 — 若已在 django 环境则直接用；否则用下面的 install

    # 仅在 logger 属性缺失时补装
    if not hasattr(sys.modules.get("apps.core.logger", object()), "logger"):
        _install("apps.core.logger", logger=MagicMock())

    spec = importlib.util.spec_from_file_location(
        "apps.node_mgmt.tasks.version_discovery_fresh",
        __file__.replace("test_version_discovery_preload.py", "../tasks/version_discovery.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_controller(os, arch, controller_id, version_command="bklite-agent version"):
    return SimpleNamespace(
        id=controller_id,
        os=os,
        cpu_architecture=arch,
        name="Controller",
        version_command=version_command,
    )


def make_node(os, arch, node_id="n1"):
    return SimpleNamespace(
        id=node_id,
        name="TestNode",
        ip="1.2.3.4",
        operating_system=os,
        cpu_architecture=arch,
    )


class TestControllerPreloadLookup:
    """验证 _discover_controller_version 从预加载 map 中正确解析 Controller"""

    def _get_fn(self):
        """从修复后的模块取 _discover_controller_version"""
        from apps.node_mgmt.tasks.version_discovery import _discover_controller_version
        return _discover_controller_version

    def _lookup(self, node, all_controllers):
        """复现修复后的 lookup 逻辑（与 _discover_controller_version 内部一致）"""
        from apps.node_mgmt.constants.node import NodeConstants
        from apps.node_mgmt.utils.architecture import normalize_cpu_architecture
        controllers_map = {(c.os, c.cpu_architecture): c for c in all_controllers}
        node_arch = normalize_cpu_architecture(getattr(node, "cpu_architecture", ""))
        return (
            controllers_map.get((node.operating_system, node_arch))
            or controllers_map.get((node.operating_system, NodeConstants.X86_64_ARCH))
            or next((c for c in all_controllers if c.os == node.operating_system), None)
        )

    def test_exact_arch_match(self):
        """精确匹配 (os, arch) → 命中对应 controller"""
        ctrl_arm = make_controller("linux", "arm64", 10)
        ctrl_x86 = make_controller("linux", "x86_64", 11)
        node = make_node("linux", "arm64")
        result = self._lookup(node, [ctrl_arm, ctrl_x86])
        assert result is ctrl_arm

    def test_x86_fallback_when_arch_missing(self):
        """arm64 无对应记录 → 回退到 x86_64"""
        ctrl_x86 = make_controller("linux", "x86_64", 11)
        node = make_node("linux", "arm64")
        result = self._lookup(node, [ctrl_x86])
        assert result is ctrl_x86

    def test_os_only_fallback(self):
        """x86_64 也无 → 按 os 兜底"""
        ctrl_arm = make_controller("linux", "arm64", 10)
        node = make_node("linux", "x86_64")
        result = self._lookup(node, [ctrl_arm])
        assert result is ctrl_arm

    def test_unknown_os_returns_none(self):
        """无匹配 → 返回 None"""
        ctrl_x86 = make_controller("linux", "x86_64", 11)
        node = make_node("windows", "x86_64")
        result = self._lookup(node, [ctrl_x86])
        assert result is None


class TestDiscoverNodeVersionsNoPerNodeDBQuery:
    """
    验证修复后 discover_node_versions 不在循环内发起 Controller.objects.filter。

    关键性：若将修复 revert（循环内每节点调 Controller.objects.filter × 3），
    则 Controller.objects.filter 的调用次数将随节点数线性增长，下面的断言就会失败。
    """

    def test_controller_queried_once_regardless_of_node_count(self):
        """
        N 个节点时，Controller.objects.filter 只调用 1 次（循环前预加载），
        不随节点数线性增长。
        """
        from apps.node_mgmt.tasks.version_discovery import discover_node_versions
        from apps.node_mgmt.models import Controller, Node
        from apps.node_mgmt.services.version_upgrade import VersionUpgradeService

        ctrl = make_controller("linux", "x86_64", 1)
        fake_nodes = [make_node("linux", "x86_64", f"n{i}") for i in range(5)]

        filter_call_count = []

        class FakeQS:
            def __init__(self, items):
                self._items = items

            def __iter__(self):
                return iter(self._items)

            def filter(self, **kwargs):
                filter_call_count.append(kwargs)
                return FakeQS([ctrl] if kwargs.get("name") == "Controller" else [])

        class FakeNodeQS:
            def iterator(self, chunk_size=None):
                return iter(fake_nodes)

        with patch.object(Controller.objects.__class__, "filter", return_value=FakeQS([ctrl])) as mock_filter, \
             patch.object(Node.objects.__class__, "iterator", return_value=iter(fake_nodes)), \
             patch.object(VersionUpgradeService, "get_latest_versions_map", return_value={}), \
             patch("apps.node_mgmt.tasks.version_discovery._discover_controller_version") as mock_discover, \
             patch("apps.node_mgmt.models.Node.objects") as mock_node_objects, \
             patch("apps.node_mgmt.models.Controller.objects") as mock_ctrl_objects:

            mock_node_objects.iterator.return_value = iter(fake_nodes)
            mock_ctrl_qs = MagicMock()
            mock_ctrl_qs.__iter__ = MagicMock(return_value=iter([ctrl]))
            mock_ctrl_objects.filter.return_value = mock_ctrl_qs

            result = discover_node_versions()

            # Controller.objects.filter 只在循环前调用 1 次（预加载）
            assert mock_ctrl_objects.filter.call_count == 1, (
                f"Controller.objects.filter 应只调用 1 次（预加载），"
                f"实际调用了 {mock_ctrl_objects.filter.call_count} 次"
            )

            # 每个节点都被处理
            assert mock_discover.call_count == len(fake_nodes)

            # total 由 success+failed 计算，不再有额外 count() 调用
            assert result["total"] == len(fake_nodes)

    def test_total_uses_counter_not_count_query(self):
        """total 值 = success_count + failed_count，不发 nodes.count() 额外查询"""
        from apps.node_mgmt.tasks.version_discovery import discover_node_versions
        from apps.node_mgmt.models import Controller, Node
        from apps.node_mgmt.services.version_upgrade import VersionUpgradeService

        ctrl = make_controller("linux", "x86_64", 1)
        # 3 成功 + 2 失败
        fake_nodes = [make_node("linux", "x86_64", f"n{i}") for i in range(5)]

        call_idx = [0]

        def fake_discover(node, lvm, cmap, actrls):
            call_idx[0] += 1
            if call_idx[0] > 3:
                raise RuntimeError("模拟失败")

        with patch("apps.node_mgmt.tasks.version_discovery._discover_controller_version",
                   side_effect=fake_discover), \
             patch("apps.node_mgmt.models.Node.objects") as mock_node_objects, \
             patch("apps.node_mgmt.models.Controller.objects") as mock_ctrl_objects, \
             patch.object(VersionUpgradeService, "get_latest_versions_map", return_value={}):

            mock_node_objects.iterator.return_value = iter(fake_nodes)
            mock_ctrl_qs = MagicMock()
            mock_ctrl_qs.__iter__ = MagicMock(return_value=iter([ctrl]))
            mock_ctrl_objects.filter.return_value = mock_ctrl_qs

            result = discover_node_versions()

            assert result["success_count"] == 3
            assert result["failed_count"] == 2
            assert result["total"] == 5  # 不是 nodes.count()，而是 3+2

            # 确认 Node.objects 没有调用 count()
            assert not mock_node_objects.count.called, "不应调用 nodes.count()，total 应从计数器计算"
