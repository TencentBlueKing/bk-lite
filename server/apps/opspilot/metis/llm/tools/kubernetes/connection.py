import io
import json
from typing import Any, Dict, Literal, Optional

from langchain_core.runnables import RunnableConfig

from apps.opspilot.metis.llm.tools.common.credentials import CredentialItem, NormalizedCredentials, normalize_credentials

KUBERNETES_INSTANCE_FIELDS = (
    "id",
    "name",
    "kubeconfig_data",
)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_kubernetes_instance(
    instance: Dict[str, Any],
    fallback_name: str = "Kubernetes - 1",
    fallback_id: str = "k8s-1",
) -> Dict[str, Any]:
    normalized = {key: instance.get(key) for key in KUBERNETES_INSTANCE_FIELDS}
    normalized["id"] = _normalize_text(normalized.get("id")) or fallback_id
    normalized["name"] = _normalize_text(normalized.get("name")) or fallback_name
    normalized["kubeconfig_data"] = _normalize_text(normalized.get("kubeconfig_data"))
    return normalized


def parse_kubernetes_instances(raw_instances: Any) -> list[Dict[str, Any]]:
    if not raw_instances:
        return []

    parsed_instances = raw_instances
    if isinstance(raw_instances, str):
        try:
            parsed_instances = json.loads(raw_instances)
        except json.JSONDecodeError:
            return []

    if not isinstance(parsed_instances, list):
        return []

    normalized_instances = []
    for index, instance in enumerate(parsed_instances, start=1):
        if not isinstance(instance, dict):
            continue
        normalized_instances.append(
            normalize_kubernetes_instance(
                instance,
                fallback_name=f"Kubernetes - {index}",
                fallback_id=f"k8s-{index}",
            )
        )
    return normalized_instances


def get_kubernetes_instances_from_configurable(
    configurable: Dict[str, Any],
) -> tuple[list[Dict[str, Any]], str]:
    instances = parse_kubernetes_instances(configurable.get("kubernetes_instances"))
    default_instance_id = _normalize_text(configurable.get("kubernetes_default_instance_id"))
    return instances, default_instance_id


def resolve_kubernetes_instance(
    instances: list[Dict[str, Any]],
    default_instance_id: str = "",
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not instances:
        raise ValueError("No Kubernetes instances configured")

    if instance_id:
        for instance in instances:
            if instance.get("id") == instance_id:
                return instance
        raise ValueError(f"Kubernetes instance not found: {instance_id}")

    if instance_name:
        for instance in instances:
            if instance.get("name") == instance_name:
                return instance
        raise ValueError(f"Kubernetes instance not found: {instance_name}")

    if default_instance_id:
        for instance in instances:
            if instance.get("id") == default_instance_id:
                return instance

    return instances[0]


def _build_legacy_kubernetes_config(
    configurable: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "kubeconfig_data": configurable.get("kubeconfig_data", ""),
    }


def build_kubernetes_config_from_instance(
    instance: Dict[str, Any],
) -> Dict[str, Any]:
    normalized = normalize_kubernetes_instance(instance)
    return {
        "kubeconfig_data": normalized.get("kubeconfig_data") or "",
    }


KUBERNETES_FLAT_FIELDS = ["kubeconfig_data"]


class KubernetesCredentialAdapter:
    flat_fields = KUBERNETES_FLAT_FIELDS

    def build_from_flat_config(
        self,
        configurable: Dict[str, Any],
    ) -> Dict[str, Any]:
        return _build_legacy_kubernetes_config(configurable)

    def build_from_credential_item(
        self,
        item: Dict[str, Any],
    ) -> Dict[str, Any]:
        return build_kubernetes_config_from_instance(item)

    def validate(self, config: Dict[str, Any]) -> None:
        pass  # kubeconfig_data is optional; falls back to ~/.kube/config

    def get_display_name(self, source: Dict[str, Any], index: int) -> str:
        return source.get("name") or f"Kubernetes - {index + 1}"


_kubernetes_adapter = KubernetesCredentialAdapter()


def build_kubernetes_normalized_from_runnable(
    config: Optional[RunnableConfig],
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> NormalizedCredentials:
    configurable = config.get("configurable", {}) if config else {}
    instances, default_instance_id = get_kubernetes_instances_from_configurable(configurable)

    if instances:
        if instance_name or instance_id:
            instance = resolve_kubernetes_instance(
                instances,
                default_instance_id,
                instance_name=instance_name,
                instance_id=instance_id,
            )
            k8s_config = build_kubernetes_config_from_instance(instance)
            return NormalizedCredentials(
                mode="single",
                legacy_single=False,
                items=[
                    CredentialItem(
                        index=0,
                        name=instance.get("name", "Kubernetes - 1"),
                        raw=instance,
                        config=k8s_config,
                    )
                ],
            )

        mode: Literal["single", "multi"] = "single" if len(instances) == 1 else "multi"
        items = []
        for i, instance in enumerate(instances):
            k8s_config = build_kubernetes_config_from_instance(instance)
            items.append(
                CredentialItem(
                    index=i,
                    name=instance.get("name", f"Kubernetes - {i + 1}"),
                    raw=instance,
                    config=k8s_config,
                )
            )
        return NormalizedCredentials(
            mode=mode,
            legacy_single=False,
            items=items,
        )

    return normalize_credentials(configurable, _kubernetes_adapter)


def test_kubernetes_instance(instance: Dict[str, Any]) -> bool:
    from kubernetes import client
    from kubernetes import config as kube_config

    from apps.opspilot.metis.llm.tools.kubernetes.utils import _preprocess_kubeconfig

    normalized = normalize_kubernetes_instance(instance)
    kubeconfig_data = normalized.get("kubeconfig_data", "")

    if kubeconfig_data:
        if isinstance(kubeconfig_data, str):
            kubeconfig_data = kubeconfig_data.replace("\\n", "\n")
        kubeconfig_data = _preprocess_kubeconfig(kubeconfig_data)
        kubeconfig_io = io.StringIO(kubeconfig_data)
        kube_config.load_kube_config(config_file=kubeconfig_io)
    else:
        try:
            kube_config.load_kube_config()
        except Exception:
            kube_config.load_incluster_config()

    v1 = client.CoreV1Api()
    v1.list_namespace()
    return True


def get_kubernetes_instances_prompt(configurable: Dict[str, Any]) -> str:
    instances, default_instance_id = get_kubernetes_instances_from_configurable(configurable)
    if not instances:
        return ""

    default_instance = resolve_kubernetes_instance(
        instances,
        default_instance_id,
    )
    available_instances = ", ".join(instance["name"] for instance in instances if instance.get("name"))
    return (
        f"已配置 {len(instances)} 个 Kubernetes 实例，"
        f"可用实例: {available_instances}。"
        f"默认实例为「{default_instance['name']}」。"
        "当用户未指定实例时，直接使用默认实例执行工具调用，无需向用户询问。"
        "仅当用户明确要求切换实例时，才在工具调用中传入 instance_name 或 instance_id 参数。"
    )
