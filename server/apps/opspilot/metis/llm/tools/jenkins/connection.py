import json
from typing import Any, Dict, Literal, Optional

import jenkins
from langchain_core.runnables import RunnableConfig

from apps.opspilot.metis.llm.tools.common.credentials import CredentialItem, CredentialValidationError, NormalizedCredentials, normalize_credentials

JENKINS_INSTANCE_FIELDS = (
    "id",
    "name",
    "jenkins_url",
    "jenkins_username",
    "jenkins_password",
)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_jenkins_instance(
    instance: Dict[str, Any],
    fallback_name: str = "Jenkins - 1",
    fallback_id: str = "jenkins-1",
) -> Dict[str, Any]:
    normalized = {key: instance.get(key) for key in JENKINS_INSTANCE_FIELDS}
    normalized["id"] = _normalize_text(normalized.get("id")) or fallback_id
    normalized["name"] = _normalize_text(normalized.get("name")) or fallback_name
    normalized["jenkins_url"] = _normalize_text(normalized.get("jenkins_url"))
    normalized["jenkins_username"] = _normalize_text(normalized.get("jenkins_username"))
    normalized["jenkins_password"] = _normalize_text(normalized.get("jenkins_password"))
    return normalized


def parse_jenkins_instances(raw_instances: Any) -> list[Dict[str, Any]]:
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
            normalize_jenkins_instance(
                instance,
                fallback_name=f"Jenkins - {index}",
                fallback_id=f"jenkins-{index}",
            )
        )
    return normalized_instances


def get_jenkins_instances_from_configurable(
    configurable: Dict[str, Any],
) -> tuple[list[Dict[str, Any]], str]:
    instances = parse_jenkins_instances(configurable.get("jenkins_instances"))
    default_instance_id = _normalize_text(configurable.get("jenkins_default_instance_id"))
    return instances, default_instance_id


def resolve_jenkins_instance(
    instances: list[Dict[str, Any]],
    default_instance_id: str = "",
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not instances:
        raise ValueError("No Jenkins instances configured")

    if instance_id:
        for instance in instances:
            if instance.get("id") == instance_id:
                return instance
        raise ValueError(f"Jenkins instance not found: {instance_id}")

    if instance_name:
        for instance in instances:
            if instance.get("name") == instance_name:
                return instance
        raise ValueError(f"Jenkins instance not found: {instance_name}")

    if default_instance_id:
        for instance in instances:
            if instance.get("id") == default_instance_id:
                return instance

    return instances[0]


def _build_legacy_jenkins_config(
    configurable: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "jenkins_url": configurable.get("jenkins_url", ""),
        "jenkins_username": configurable.get("jenkins_username", ""),
        "jenkins_password": configurable.get("jenkins_password", ""),
    }


def build_jenkins_config_from_instance(
    instance: Dict[str, Any],
) -> Dict[str, Any]:
    normalized = normalize_jenkins_instance(instance)
    return {
        "jenkins_url": normalized.get("jenkins_url") or "",
        "jenkins_username": normalized.get("jenkins_username") or "",
        "jenkins_password": normalized.get("jenkins_password") or "",
    }


JENKINS_FLAT_FIELDS = ["jenkins_url", "jenkins_username", "jenkins_password"]


class JenkinsCredentialAdapter:
    flat_fields = JENKINS_FLAT_FIELDS

    def build_from_flat_config(
        self,
        configurable: Dict[str, Any],
    ) -> Dict[str, Any]:
        return _build_legacy_jenkins_config(configurable)

    def build_from_credential_item(
        self,
        item: Dict[str, Any],
    ) -> Dict[str, Any]:
        return build_jenkins_config_from_instance(item)

    def validate(self, config: Dict[str, Any]) -> None:
        if not config.get("jenkins_url"):
            raise CredentialValidationError("Jenkins URL is required")

    def get_display_name(self, source: Dict[str, Any], index: int) -> str:
        return source.get("name") or f"Jenkins - {index + 1}"


_jenkins_adapter = JenkinsCredentialAdapter()


def build_jenkins_normalized_from_runnable(
    config: Optional[RunnableConfig],
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> NormalizedCredentials:
    configurable = config.get("configurable", {}) if config else {}
    instances, default_instance_id = get_jenkins_instances_from_configurable(configurable)

    if instances:
        if instance_name or instance_id:
            instance = resolve_jenkins_instance(
                instances,
                default_instance_id,
                instance_name=instance_name,
                instance_id=instance_id,
            )
            jenkins_config = build_jenkins_config_from_instance(instance)
            return NormalizedCredentials(
                mode="single",
                legacy_single=False,
                items=[
                    CredentialItem(
                        index=0,
                        name=instance.get("name", "Jenkins - 1"),
                        raw=instance,
                        config=jenkins_config,
                    )
                ],
            )

        mode: Literal["single", "multi"] = "single" if len(instances) == 1 else "multi"
        items = []
        for i, instance in enumerate(instances):
            jenkins_config = build_jenkins_config_from_instance(instance)
            items.append(
                CredentialItem(
                    index=i,
                    name=instance.get("name", f"Jenkins - {i + 1}"),
                    raw=instance,
                    config=jenkins_config,
                )
            )
        return NormalizedCredentials(
            mode=mode,
            legacy_single=False,
            items=items,
        )

    return normalize_credentials(configurable, _jenkins_adapter)


def test_jenkins_instance(instance: Dict[str, Any]) -> bool:
    normalized = normalize_jenkins_instance(instance)
    if not normalized.get("jenkins_url"):
        raise ValueError("Jenkins URL is required")
    cfg = build_jenkins_config_from_instance(normalized)
    client = jenkins.Jenkins(
        cfg["jenkins_url"],
        username=cfg["jenkins_username"],
        password=cfg["jenkins_password"],
    )
    client.get_jobs()
    return True


def get_jenkins_instances_prompt(configurable: Dict[str, Any]) -> str:
    instances, default_instance_id = get_jenkins_instances_from_configurable(configurable)
    if not instances:
        return ""

    default_instance = resolve_jenkins_instance(instances, default_instance_id)
    available_instances = ", ".join(instance["name"] for instance in instances if instance.get("name"))
    return (
        f"已配置 {len(instances)} 个 Jenkins 实例，可用实例: {available_instances}。"
        f"默认实例为「{default_instance['name']}」。"
        "当用户未指定实例时，直接使用默认实例执行工具调用，无需向用户询问。"
        "仅当用户明确要求切换实例时，才在工具调用中传入 instance_name 或 instance_id 参数。"
    )
