"""Issue 5854：SNMP 模板指纹保存失败时必须回滚已下发的节点配置。"""

from types import SimpleNamespace
from unittest import mock

import pytest

import apps.node_mgmt  # noqa: F401 - monitor.nats.monitor 启动依赖
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.services.collect_config_update import sha256_text
from apps.monitor.services.custom_snmp_plugin import CustomSnmpPluginService

pytestmark = pytest.mark.unit


OLD_APPLIED = {
    "applied_content_sha256": "old-fp",
    "applied_rendered_sha256": "old-rendered",
    "applied_pack_version": "v1",
    "content_hand_edited": True,
}


class FakeCollectConfig:
    def __init__(self, config_id, *, fail_save=False):
        self.id = config_id
        self.monitor_plugin = SimpleNamespace(pack_content_sha256="new-fp", pack_version="v2")
        self.applied_content_sha256 = OLD_APPLIED["applied_content_sha256"]
        self.applied_rendered_sha256 = OLD_APPLIED["applied_rendered_sha256"]
        self.applied_pack_version = OLD_APPLIED["applied_pack_version"]
        self.content_hand_edited = OLD_APPLIED["content_hand_edited"]
        self.updated_at = None
        self.fail_save = fail_save
        self.save_calls = 0
        self.persisted = dict(OLD_APPLIED)

    def save(self, update_fields=None):
        self.save_calls += 1
        if self.fail_save:
            raise RuntimeError("fingerprint save fail")
        self.persisted = {
            "applied_content_sha256": self.applied_content_sha256,
            "applied_rendered_sha256": self.applied_rendered_sha256,
            "applied_pack_version": self.applied_pack_version,
            "content_hand_edited": self.content_hand_edited,
        }


class FakeQuerySet:
    def __init__(self, configs):
        self._configs = configs

    def select_related(self, *args, **kwargs):
        return self._configs


class FakeNodeMgmt:
    def __init__(self, initial, *, fail_on_content=None):
        self.state = dict(initial)
        self.calls = []
        self.fail_on_content = fail_on_content

    def update_child_config_content(self, cid, content):
        self.calls.append((cid, content))
        if self.fail_on_content is not None and content == self.fail_on_content:
            raise RuntimeError("apply fail")
        self.state[cid] = content


def _patch_collect_configs(configs):
    fake_model = mock.Mock()
    fake_model.objects.filter.return_value = FakeQuerySet(configs)
    return mock.patch("apps.monitor.models.CollectConfig", fake_model)


def _two_item_plan():
    return [
        {"id": "cfg-a", "rendered_content": "new-a", "original_content": "orig-a"},
        {"id": "cfg-b", "rendered_content": "new-b", "original_content": "orig-b"},
    ]


class TestPropagateCollectTemplateRollback:
    def test_空计划直接返回且不实例化NodeMgmt(self):
        with mock.patch("apps.monitor.services.custom_snmp_plugin.NodeMgmt") as node_cls:
            assert CustomSnmpPluginService.propagate_collect_template([]) is None
            node_cls.assert_not_called()

    def test_指纹保存失败回滚节点到original_content(self):
        node_mgmt = FakeNodeMgmt({"cfg-a": "orig-a", "cfg-b": "orig-b"})
        cfg_a = FakeCollectConfig("cfg-a", fail_save=True)
        cfg_b = FakeCollectConfig("cfg-b")
        plan = _two_item_plan()

        with mock.patch("apps.monitor.services.custom_snmp_plugin.NodeMgmt", return_value=node_mgmt):
            with _patch_collect_configs([cfg_a, cfg_b]):
                with pytest.raises(BaseAppException) as exc:
                    CustomSnmpPluginService.propagate_collect_template(plan)

        assert "采集模板同步失败" in str(exc.value)
        assert node_mgmt.state["cfg-a"] == "orig-a"
        assert node_mgmt.state["cfg-b"] == "orig-b"
        assert ("cfg-a", "new-a") in node_mgmt.calls
        assert ("cfg-b", "new-b") in node_mgmt.calls
        assert node_mgmt.calls[-2:] == [("cfg-b", "orig-b"), ("cfg-a", "orig-a")]
        assert cfg_a.persisted == OLD_APPLIED
        assert cfg_b.persisted == OLD_APPLIED
        assert cfg_a.save_calls == 1
        assert cfg_b.save_calls == 0

    def test_下发中途失败仍逆序回滚(self):
        node_mgmt = FakeNodeMgmt({"cfg-a": "orig-a", "cfg-b": "orig-b"}, fail_on_content="new-b")
        plan = _two_item_plan()

        with mock.patch("apps.monitor.services.custom_snmp_plugin.NodeMgmt", return_value=node_mgmt):
            with pytest.raises(BaseAppException) as exc:
                CustomSnmpPluginService.propagate_collect_template(plan)

        assert "采集模板同步失败" in str(exc.value)
        assert node_mgmt.state["cfg-a"] == "orig-a"
        assert node_mgmt.state["cfg-b"] == "orig-b"
        assert node_mgmt.calls == [
            ("cfg-a", "new-a"),
            ("cfg-b", "new-b"),
            ("cfg-a", "orig-a"),
        ]

    def test_成功路径节点内容与指纹一致(self):
        node_mgmt = FakeNodeMgmt({"cfg-a": "orig-a", "cfg-b": "orig-b"})
        cfg_a = FakeCollectConfig("cfg-a")
        cfg_b = FakeCollectConfig("cfg-b")
        plan = _two_item_plan()

        with mock.patch("apps.monitor.services.custom_snmp_plugin.NodeMgmt", return_value=node_mgmt):
            with _patch_collect_configs([cfg_a, cfg_b]):
                CustomSnmpPluginService.propagate_collect_template(plan)

        assert node_mgmt.state == {"cfg-a": "new-a", "cfg-b": "new-b"}
        assert cfg_a.persisted["applied_content_sha256"] == "new-fp"
        assert cfg_b.persisted["applied_content_sha256"] == "new-fp"
        assert cfg_a.persisted["applied_pack_version"] == "v2"
        assert cfg_b.persisted["applied_pack_version"] == "v2"
        assert cfg_a.persisted["content_hand_edited"] is False
        assert cfg_b.persisted["content_hand_edited"] is False
        assert cfg_a.persisted["applied_rendered_sha256"] == sha256_text("new-a")
        assert cfg_b.persisted["applied_rendered_sha256"] == sha256_text("new-b")
        assert ("cfg-a", "orig-a") not in node_mgmt.calls
        assert ("cfg-b", "orig-b") not in node_mgmt.calls


class TestUpdateCollectTemplateValidationUnchanged:
    def _plugin(self):
        return SimpleNamespace(id=1, template_id="t1")

    def test_空片段抛异常(self):
        with pytest.raises(BaseAppException) as exc:
            CustomSnmpPluginService.update_collect_template(self._plugin(), "   ")
        assert "采集片段不能为空" in str(exc.value)

    def test_包含主配置节抛异常(self):
        with pytest.raises(BaseAppException) as exc:
            CustomSnmpPluginService.update_collect_template(self._plugin(), "[[inputs.snmp]]\n oid='x'")
        assert "主配置" in str(exc.value)

    def test_包含模板语法抛异常(self):
        with pytest.raises(BaseAppException) as exc:
            CustomSnmpPluginService.update_collect_template(self._plugin(), "[[inputs.snmp.field]]\n name = {{ x }}")
        assert "模板语法" in str(exc.value)

    def test_指纹保存失败外层恢复模板(self):
        plugin = self._plugin()
        child_template = SimpleNamespace(id="tmpl-1", content="original-template")
        restored = {}

        class FakeTemplateQS:
            def filter(self, **kwargs):
                restored["content"] = kwargs.get("content") or restored.get("content")
                if "id" in kwargs:
                    restored["id"] = kwargs["id"]
                return self

            def update(self, **kwargs):
                restored.update(kwargs)
                return 1

            def select_for_update(self):
                return self

            def first(self):
                return child_template

        with mock.patch.object(CustomSnmpPluginService, "get_child_template", return_value=child_template):
            with mock.patch.object(CustomSnmpPluginService, "_replace_collect_snippet", return_value="updated-template"):
                with mock.patch.object(CustomSnmpPluginService, "_validate_child_template"):
                    with mock.patch.object(
                        CustomSnmpPluginService,
                        "_build_propagation_plan",
                        return_value=_two_item_plan(),
                    ):
                        with mock.patch(
                            "apps.monitor.services.custom_snmp_plugin.MonitorPluginConfigTemplate"
                        ) as tmpl_model:
                            tmpl_model.objects = FakeTemplateQS()
                            child_template.save = mock.Mock()
                            node_mgmt = FakeNodeMgmt({"cfg-a": "orig-a", "cfg-b": "orig-b"})
                            cfg_a = FakeCollectConfig("cfg-a", fail_save=True)
                            cfg_b = FakeCollectConfig("cfg-b")
                            with mock.patch(
                                "apps.monitor.services.custom_snmp_plugin.NodeMgmt",
                                return_value=node_mgmt,
                            ):
                                with _patch_collect_configs([cfg_a, cfg_b]):
                                    with mock.patch("apps.monitor.services.custom_snmp_plugin.transaction.atomic"):
                                        with pytest.raises(BaseAppException):
                                            CustomSnmpPluginService.update_collect_template(
                                                plugin,
                                                "[[inputs.snmp.field]]\n  oid = \".1\"\n  name = \"uptime\"\n",
                                            )

        assert restored.get("content") == "original-template"
        assert node_mgmt.state["cfg-a"] == "orig-a"
        assert node_mgmt.state["cfg-b"] == "orig-b"
