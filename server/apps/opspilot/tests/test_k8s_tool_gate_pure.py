"""opspilot.metis.llm.chain.k8s_tool_gate.is_k8s_agent 纯逻辑测试。

规格（F058 报告工具门控）：仅当工具池含 K8s 标记工具或名称含 kubernetes/kubectl
子串时，agent 才被判定为 K8s-flavoured，从而决定是否绑定两个 K8s 报告工具。
判定只看工具 .name，缺名忽略。
"""

import pytest

from apps.opspilot.metis.llm.chain.k8s_tool_gate import is_k8s_agent

pytestmark = pytest.mark.unit


class _Tool:
    def __init__(self, name):
        self.name = name


class TestIsK8sAgent:
    def test_标记工具触发判定(self):
        assert is_k8s_agent([_Tool("analyze_deployment_configurations")]) is True

    @pytest.mark.parametrize(
        "name",
        [
            "list_kubernetes_pods",
            "get_kubernetes_resource",
            "kubectl_apply",
            "run_kubectl_command",
            "KUBERNETES_TOPOLOGY",  # 大小写不敏感
        ],
    )
    def test_名称含子串触发判定(self, name):
        assert is_k8s_agent([_Tool(name)]) is True

    def test_无关工具不触发(self):
        tools = [_Tool("mysql_query"), _Tool("redis_get"), _Tool("send_email")]
        assert is_k8s_agent(tools) is False

    def test_混合池中存在一个_k8s_工具即触发(self):
        tools = [_Tool("mysql_query"), _Tool("list_kubernetes_pods"), _Tool("redis_get")]
        assert is_k8s_agent(tools) is True

    def test_空工具池返回_false(self):
        assert is_k8s_agent([]) is False

    def test_none_工具池返回_false(self):
        assert is_k8s_agent(None) is False

    def test_缺名工具被忽略(self):
        class _NoName:
            pass

        assert is_k8s_agent([_NoName()]) is False

    def test_空名字符串被忽略(self):
        assert is_k8s_agent([_Tool("")]) is False

    def test_name_为_none_安全处理(self):
        assert is_k8s_agent([_Tool(None)]) is False

    def test_子串不在工具名内不触发(self):
        # "k8s" 不在子串列表里（只有 kubernetes/kubectl），故纯 k8s 命名不触发
        assert is_k8s_agent([_Tool("k8s_helper")]) is False
