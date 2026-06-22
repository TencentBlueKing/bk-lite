import pytest

from apps.opspilot.metis.llm.chain.node import ToolsNodes
from apps.opspilot.metis.llm.tools.common.user_choice_guard import (
    ChoiceOptionGuard,
    validate_user_choice_options,
)
from apps.opspilot.metis.llm.tools.kubernetes.user_choice_guard import (
    build_kubernetes_cluster_choice_guard,
)


def test_common_guard_blocks_fabricated_options_for_any_target_type():
    message = validate_user_choice_options(
        question_type="single_select",
        options=["实例A", "实例B"],
        guard=ChoiceOptionGuard(
            target_label="MSSQL 实例",
            allowed_options=["mssql-prod", "mssql-standby"],
        ),
    )

    assert "MSSQL 实例选择项不是来自真实配置" in message
    assert "mssql-prod" in message
    assert "mssql-standby" in message
    assert "实例A" in message


def test_common_guard_allows_real_options_for_any_target_type():
    message = validate_user_choice_options(
        question_type="single_select",
        options=["mssql-prod", "mssql-standby"],
        guard=ChoiceOptionGuard(
            target_label="MSSQL 实例",
            allowed_options=["mssql-prod", "mssql-standby"],
        ),
    )

    assert message == ""


def test_kubernetes_guard_blocks_cluster_choice_when_only_one_instance():
    guard = build_kubernetes_cluster_choice_guard(
        question="当前环境下有多个 Kubernetes 集群，请选择需要检查配置健康的集群：",
        options=["集群A", "集群B", "集群C"],
        configurable={
            "kubernetes_instances": [
                {
                    "id": "k8s-1",
                    "name": "Kubernetes - 1",
                    "kubeconfig_data": "apiVersion: v1",
                }
            ]
        },
    )

    message = validate_user_choice_options(
        question_type="single_select",
        options=["集群A", "集群B", "集群C"],
        guard=guard,
    )

    assert "当前仅配置 1 个 Kubernetes 集群" in message
    assert "禁止向用户询问选择集群" in message
    assert "Kubernetes - 1" in message


def test_kubernetes_guard_uses_user_message_when_choice_question_omits_k8s():
    guard = build_kubernetes_cluster_choice_guard(
        question="检测到多个集群，请选择要扫描的集群范围。",
        options=["集群A", "集群B", "集群C"],
        configurable={
            "graph_request": type(
                "GraphRequest",
                (),
                {
                    "graph_user_message": "查看下k8s集群所有工作负载有没有问题",
                    "user_message": "查看下k8s集群所有工作负载有没有问题",
                },
            )(),
            "kubernetes_instances": [
                {
                    "id": "k8s-1",
                    "name": "Kubernetes - 1",
                    "kubeconfig_data": "apiVersion: v1",
                }
            ],
        },
    )

    message = validate_user_choice_options(
        question_type="single_select",
        options=["集群A", "集群B", "集群C"],
        guard=guard,
    )

    assert "当前仅配置 1 个 Kubernetes 集群" in message
    assert "Kubernetes - 1" in message


def test_kubernetes_guard_blocks_fabricated_cluster_options_for_casual_message():
    guard = build_kubernetes_cluster_choice_guard(
        question="当前有多个集群，请选择需要检查的集群",
        options=["集群A", "集群B"],
        configurable={
            "graph_request": type(
                "GraphRequest",
                (),
                {
                    "graph_user_message": "hello~你吃饭了吗",
                    "user_message": "hello~你吃饭了吗",
                },
            )(),
            "kubernetes_instances": [
                {
                    "id": "k8s-1",
                    "name": "prod-cluster",
                    "kubeconfig_data": "apiVersion: v1",
                },
                {
                    "id": "k8s-2",
                    "name": "staging-cluster",
                    "kubeconfig_data": "apiVersion: v1",
                },
            ],
        },
    )

    message = validate_user_choice_options(
        question_type="single_select",
        options=["集群A", "集群B"],
        guard=guard,
    )

    assert "Kubernetes 集群选择项不是来自真实配置" in message
    assert "prod-cluster" in message
    assert "staging-cluster" in message
    assert "集群A" in message


def test_kubernetes_guard_blocks_english_placeholder_cluster_options_for_health_check():
    guard = build_kubernetes_cluster_choice_guard(
        question="当前有多个集群，请选择要检查健康状况的集群。",
        options=["Cluster-A", "Cluster-B", "Cluster-C"],
        configurable={
            "kubernetes_instances": [
                {
                    "id": "k8s-1",
                    "name": "Kubernetes - 1",
                    "kubeconfig_data": "apiVersion: v1",
                }
            ]
        },
    )

    message = validate_user_choice_options(
        question_type="single_select",
        options=["Cluster-A", "Cluster-B", "Cluster-C"],
        guard=guard,
    )

    assert "当前仅配置 1 个 Kubernetes 集群" in message
    assert "Kubernetes - 1" in message
    assert "Cluster-A" not in message


def test_kubernetes_guard_reads_instances_from_graph_request_extra_config():
    guard = build_kubernetes_cluster_choice_guard(
        question="检测到多个集群，请选择要扫描的集群范围。",
        options=["集群A", "集群B", "集群C"],
        configurable={
            "graph_request": type(
                "GraphRequest",
                (),
                {
                    "graph_user_message": "查看下k8s集群所有工作负载有没有问题",
                    "user_message": "查看下k8s集群所有工作负载有没有问题",
                    "extra_config": {
                        "kubernetes_instances": [
                            {
                                "id": "k8s-1",
                                "name": "Kubernetes - 1",
                                "kubeconfig_data": "apiVersion: v1",
                            }
                        ]
                    },
                },
            )(),
        },
    )

    message = validate_user_choice_options(
        question_type="single_select",
        options=["集群A", "集群B", "集群C"],
        guard=guard,
    )

    assert "当前仅配置 1 个 Kubernetes 集群" in message
    assert "Kubernetes - 1" in message


def test_kubernetes_guard_blocks_fabricated_cluster_options():
    guard = build_kubernetes_cluster_choice_guard(
        question="当前环境下有多个 Kubernetes 集群，请选择需要检查配置健康的集群：",
        options=["集群A", "集群B", "集群C"],
        configurable={
            "kubernetes_instances": [
                {
                    "id": "k8s-1",
                    "name": "prod-cluster",
                    "kubeconfig_data": "apiVersion: v1",
                },
                {
                    "id": "k8s-2",
                    "name": "staging-cluster",
                    "kubeconfig_data": "apiVersion: v1",
                },
            ]
        },
    )

    message = validate_user_choice_options(
        question_type="single_select",
        options=["集群A", "集群B", "集群C"],
        guard=guard,
    )

    assert "Kubernetes 集群选择项不是来自真实配置" in message
    assert "prod-cluster" in message
    assert "staging-cluster" in message
    assert "集群A" in message


def test_kubernetes_guard_allows_real_cluster_options():
    guard = build_kubernetes_cluster_choice_guard(
        question="当前环境下有多个 Kubernetes 集群，请选择需要检查配置健康的集群：",
        options=["prod-cluster", "staging-cluster"],
        configurable={
            "kubernetes_instances": [
                {
                    "id": "k8s-1",
                    "name": "prod-cluster",
                    "kubeconfig_data": "apiVersion: v1",
                },
                {
                    "id": "k8s-2",
                    "name": "staging-cluster",
                    "kubeconfig_data": "apiVersion: v1",
                },
            ]
        },
    )

    message = validate_user_choice_options(
        question_type="single_select",
        options=["prod-cluster", "staging-cluster"],
        guard=guard,
    )

    assert message == ""


@pytest.mark.asyncio
async def test_choice_tool_blocks_single_k8s_instance_fabricated_cluster_options(mocker):
    choice_tool = ToolsNodes()._build_choice_tool()
    choice_func = choice_tool._request_choice_func
    choice_func._configurable = {
        "kubernetes_instances": [
            {
                "id": "k8s-1",
                "name": "Kubernetes - 1",
                "kubeconfig_data": "apiVersion: v1",
            }
        ]
    }

    dispatch_mock = mocker.patch("apps.opspilot.metis.llm.chain.node.dispatch_custom_event")
    wait_mock = mocker.patch("apps.opspilot.metis.llm.chain.node.wait_for_choice")

    result = await choice_func(
        question="当前环境下有多个 Kubernetes 集群，请选择需要检查配置健康的集群：",
        question_type="single_select",
        options=["集群A", "集群B", "集群C"],
    )

    assert "当前仅配置 1 个 Kubernetes 集群" in result
    assert "禁止向用户询问选择集群" in result
    assert "Kubernetes - 1" in result
    dispatch_mock.assert_not_called()
    wait_mock.assert_not_called()
