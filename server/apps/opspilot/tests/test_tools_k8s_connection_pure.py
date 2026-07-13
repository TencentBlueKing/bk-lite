"""Kubernetes 连接配置解析单元测试 (kubernetes/connection)。

覆盖实例归一化、JSON 解析、按 id/name/kubeconfig-context 解析实例、prompt 生成、
以及多实例 NormalizedCredentials 构造。不连接真实集群。
"""

import pytest
import yaml

from apps.opspilot.metis.llm.tools.kubernetes import connection as kc


class TestNormalizeKubernetesInstance:
    def test_fallbacks(self):
        out = kc.normalize_kubernetes_instance({})
        assert out["id"] == "k8s-1"
        assert out["name"] == "Kubernetes - 1"
        assert out["kubeconfig_data"] == ""

    def test_custom_fallbacks(self):
        out = kc.normalize_kubernetes_instance({}, fallback_name="N", fallback_id="x")
        assert out["id"] == "x" and out["name"] == "N"

    def test_values_preserved(self):
        out = kc.normalize_kubernetes_instance({"id": "a", "name": "A", "kubeconfig_data": "kc"})
        assert out == {"id": "a", "name": "A", "kubeconfig_data": "kc"}


class TestParseKubernetesInstances:
    def test_empty(self):
        assert kc.parse_kubernetes_instances(None) == []

    def test_json_string(self):
        out = kc.parse_kubernetes_instances('[{"name": "A"}]')
        assert out[0]["name"] == "A"

    def test_invalid_json(self):
        assert kc.parse_kubernetes_instances("{bad") == []

    def test_non_list(self):
        assert kc.parse_kubernetes_instances('{"x":1}') == []

    def test_non_dict_skipped(self):
        out = kc.parse_kubernetes_instances([{"name": "A"}, 1, "b"])
        assert len(out) == 1


class TestResolveKubernetesInstance:
    @pytest.fixture
    def instances(self):
        return [
            {"id": "i1", "name": "Alpha", "kubeconfig_data": ""},
            {"id": "i2", "name": "Beta", "kubeconfig_data": ""},
        ]

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="No Kubernetes instances"):
            kc.resolve_kubernetes_instance([])

    def test_by_id(self, instances):
        assert kc.resolve_kubernetes_instance(instances, instance_id="i2")["name"] == "Beta"

    def test_by_id_not_found(self, instances):
        with pytest.raises(ValueError, match="not found"):
            kc.resolve_kubernetes_instance(instances, instance_id="zz")

    def test_by_name(self, instances):
        assert kc.resolve_kubernetes_instance(instances, instance_name="Alpha")["id"] == "i1"

    def test_by_name_not_found(self, instances):
        with pytest.raises(ValueError, match="not found"):
            kc.resolve_kubernetes_instance(instances, instance_name="Zeta")

    def test_name_fallback_to_kubeconfig_context(self):
        kubeconfig = yaml.safe_dump(
            {"contexts": [{"name": "ctx-prod", "context": {"cluster": "cluster-prod"}}]}
        )
        instances = [{"id": "i1", "name": "Display", "kubeconfig_data": kubeconfig}]
        # 用 context name 匹配
        assert kc.resolve_kubernetes_instance(instances, instance_name="ctx-prod")["id"] == "i1"
        # 用 cluster name 匹配
        assert kc.resolve_kubernetes_instance(instances, instance_name="cluster-prod")["id"] == "i1"

    def test_name_fallback_cluster_entry(self):
        kubeconfig = yaml.safe_dump({"clusters": [{"name": "cl-1"}]})
        instances = [{"id": "i1", "name": "Display", "kubeconfig_data": kubeconfig}]
        assert kc.resolve_kubernetes_instance(instances, instance_name="cl-1")["id"] == "i1"

    def test_default_first(self, instances):
        assert kc.resolve_kubernetes_instance(instances)["id"] == "i1"


class TestBuildConfigFromInstance:
    def test_extracts_kubeconfig(self):
        out = kc.build_kubernetes_config_from_instance({"kubeconfig_data": "kc-data"})
        assert out == {"kubeconfig_data": "kc-data"}

    def test_empty_default(self):
        out = kc.build_kubernetes_config_from_instance({})
        assert out == {"kubeconfig_data": ""}


class TestPrompt:
    def test_empty_no_instances(self):
        assert kc.get_kubernetes_instances_prompt({}) == ""

    def test_lists_names_and_count(self):
        configurable = {"kubernetes_instances": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]}
        prompt = kc.get_kubernetes_instances_prompt(configurable)
        assert "2 个 Kubernetes 实例" in prompt
        assert "A" in prompt and "B" in prompt


class TestBuildNormalizedFromRunnable:
    def test_multi_instances_mode(self):
        cfg = {"configurable": {"kubernetes_instances": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]}}
        out = kc.build_kubernetes_normalized_from_runnable(cfg)
        assert out["mode"] == "multi"
        assert len(out["items"]) == 2

    def test_single_instance_mode(self):
        cfg = {"configurable": {"kubernetes_instances": [{"id": "a", "name": "A"}]}}
        out = kc.build_kubernetes_normalized_from_runnable(cfg)
        assert out["mode"] == "single"
        assert len(out["items"]) == 1

    def test_explicit_selection_single(self):
        cfg = {"configurable": {"kubernetes_instances": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]}}
        out = kc.build_kubernetes_normalized_from_runnable(cfg, instance_name="B")
        assert out["mode"] == "single"
        assert out["items"][0]["name"] == "B"
