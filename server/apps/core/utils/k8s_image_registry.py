import ipaddress
import json
import re
import shlex

from apps.core.exceptions.base_app_exception import ValidationAppException

DEFAULT_K8S_IMAGE_REGISTRY_PREFIX = "bk-lite.tencentcloudcr.com/bklite"
MAX_K8S_IMAGE_REGISTRY_PREFIX_LENGTH = 255

_HOST_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_IPV4_PATTERN = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_REPOSITORY_COMPONENT_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


def normalize_k8s_image_registry_prefix(value=None) -> str:
    """规范化并校验 K8s 采集器镜像仓库前缀。"""
    if value is None or value == "":
        return DEFAULT_K8S_IMAGE_REGISTRY_PREFIX
    if not isinstance(value, str):
        raise ValidationAppException("镜像仓库前缀格式不正确")
    if len(value) > MAX_K8S_IMAGE_REGISTRY_PREFIX_LENGTH:
        raise ValidationAppException("镜像仓库前缀长度不能超过 255 个字符")
    if value != value.strip() or any(character.isspace() or ord(character) < 32 for character in value):
        raise ValidationAppException("镜像仓库前缀不能包含空白或控制字符")
    if "://" in value:
        raise ValidationAppException("镜像仓库前缀不能包含协议头")

    normalized = value.rstrip("/")
    if not normalized or normalized != value:
        raise ValidationAppException("镜像仓库前缀不能以 / 结尾")

    host_port, *repository_components = normalized.split("/")
    if not repository_components:
        raise ValidationAppException("镜像仓库前缀必须包含仓库路径")

    if host_port.startswith("["):
        match = re.fullmatch(r"\[([^]]+)](?::(\d{1,5}))?", host_port)
        if not match:
            raise ValidationAppException("镜像仓库地址格式不正确")
        try:
            ipaddress.IPv6Address(match.group(1))
        except ValueError as error:
            raise ValidationAppException("镜像仓库 IPv6 地址格式不正确") from error
        port = match.group(2)
    else:
        if host_port.count(":") > 1:
            raise ValidationAppException("IPv6 镜像仓库地址必须使用方括号")
        host, separator, port = host_port.partition(":")
        if _IPV4_PATTERN.fullmatch(host):
            try:
                ipaddress.IPv4Address(host)
            except ValueError as error:
                raise ValidationAppException("镜像仓库 IPv4 地址格式不正确") from error

        elif not all(_HOST_LABEL_PATTERN.fullmatch(label) for label in host.split(".")):
            raise ValidationAppException("镜像仓库主机名格式不正确")
        if separator and not port:
            raise ValidationAppException("镜像仓库端口格式不正确")

    if port and (not port.isdigit() or not 1 <= int(port) <= 65535):
        raise ValidationAppException("镜像仓库端口必须在 1 到 65535 之间")
    if not all(_REPOSITORY_COMPONENT_PATTERN.fullmatch(component) for component in repository_components):
        raise ValidationAppException("镜像仓库路径仅允许小写字母、数字、点、下划线和连字符")
    return normalized


def build_kubectl_install_command(api_url: str, token: str) -> str:
    """用 JSON 与 shell 安全序列化生成安装命令。"""
    payload = json.dumps({"token": token}, ensure_ascii=False, separators=(",", ":"))
    return "curl -sSLk -X POST -H 'Content-Type: application/json' " f"{shlex.quote(api_url)} -d {shlex.quote(payload)} | kubectl apply -f -"
