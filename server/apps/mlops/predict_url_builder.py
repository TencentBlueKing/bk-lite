import os
from collections.abc import Mapping
from urllib.parse import urlparse

SERVING_PORT_NOT_CONFIGURED = "error.serving_port_not_configured"
SERVING_HOST_NOT_CONFIGURED = "error.serving_host_not_configured"


def sanitize_k8s_name(name: str) -> str:
    return name.lower().replace("_", "-")


def get_host_address() -> str:
    node_server_url = os.getenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "")
    if not node_server_url:
        return ""

    parsed = urlparse(node_server_url)
    return parsed.hostname or ""


def build_predict_url(serving_id: str, container_info: Mapping[str, object] | None) -> str:
    container_info = container_info or {}
    runtime = os.getenv("MLOPS_RUNTIME", "docker").lower()

    port = container_info.get("port")
    if not port:
        raise ValueError(SERVING_PORT_NOT_CONFIGURED)

    if runtime == "kubernetes":
        namespace = os.getenv("MLOPS_KUBERNETES_NAMESPACE", "mlops")
        service_name = f"{sanitize_k8s_name(serving_id)}-svc"
        return f"http://{service_name}.{namespace}.svc.cluster.local:3000/predict"

    if runtime == "docker":
        return f"http://{serving_id}:3000/predict"

    host_address = get_host_address()
    if host_address:
        return f"http://{host_address}:{port}/predict"

    raise ValueError(SERVING_HOST_NOT_CONFIGURED)
