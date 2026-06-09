import re
from typing import Any, Dict, Optional

from apps.opspilot.metis.llm.tools.common.user_choice_guard import ChoiceOptionGuard
from apps.opspilot.metis.llm.tools.kubernetes.connection import parse_kubernetes_instances


KUBERNETES_CLUSTER_ALIASES = {"全部", "所有集群", "全部集群", "All"}
PLACEHOLDER_CLUSTER_OPTION_PATTERN = re.compile(
    r"^(?:集群\s*[A-ZＡ-ＺA-Za-z0-9]+|cluster\s*[-_]?\s*[A-Z0-9]+)$",
    re.IGNORECASE,
)


def _contains_kubernetes_keyword(text: str) -> bool:
    return any(keyword in (text or "") for keyword in ("Kubernetes", "kubernetes", "K8s", "k8s", "K8S"))


def _get_user_message(configurable: Dict[str, Any]) -> str:
    graph_request = (configurable or {}).get("graph_request")
    messages = [
        getattr(graph_request, "graph_user_message", ""),
        getattr(graph_request, "user_message", ""),
    ]
    return " ".join(message for message in messages if isinstance(message, str))


def _get_kubernetes_instances_raw(configurable: Dict[str, Any]) -> Any:
    configurable = configurable or {}
    if configurable.get("kubernetes_instances"):
        return configurable.get("kubernetes_instances")

    graph_request = configurable.get("graph_request")
    extra_config = getattr(graph_request, "extra_config", None) or {}
    if isinstance(extra_config, dict):
        return extra_config.get("kubernetes_instances")
    return None


def is_kubernetes_cluster_choice(question: str, options: Optional[list[str]], context: str = "") -> bool:
    if not options:
        return False
    text = question or ""
    mentions_k8s = _contains_kubernetes_keyword(text) or _contains_kubernetes_keyword(context)
    mentions_cluster = "集群" in text or "cluster" in text.lower()
    placeholder_cluster_options = all(
        bool(PLACEHOLDER_CLUSTER_OPTION_PATTERN.match((option or "").strip()))
        for option in options
    )
    return mentions_cluster and (mentions_k8s or placeholder_cluster_options)


def build_kubernetes_cluster_choice_guard(
    *,
    question: str,
    options: Optional[list[str]],
    configurable: Dict[str, Any],
) -> Optional[ChoiceOptionGuard]:
    user_message = _get_user_message(configurable)
    if not is_kubernetes_cluster_choice(question, options, context=user_message):
        return None

    instances = parse_kubernetes_instances(_get_kubernetes_instances_raw(configurable))
    if not instances:
        return None

    instance_names = [str(instance.get("name") or "") for instance in instances if instance.get("name")]
    single_option_message = ""
    if len(instance_names) == 1:
        single_option_message = (
            f"检测到当前仅配置 1 个 Kubernetes 集群「{instance_names[0]}」，"
            "禁止向用户询问选择集群。请直接使用该集群继续调用 Kubernetes 工具。"
        )

    return ChoiceOptionGuard(
        target_label="Kubernetes 集群",
        allowed_options=instance_names,
        allowed_aliases=KUBERNETES_CLUSTER_ALIASES,
        single_option_message=single_option_message,
    )
