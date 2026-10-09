import os

DEFAULT_NATS_NAMESPACE = "bklite"


def resolve_nats_namespace():
    """读取部署配置 NATS_NAMESPACE；未配置或为空白时回退为 bklite。"""
    from django.conf import settings

    configured = getattr(settings, "NATS_NAMESPACE", None)
    if not isinstance(configured, str) or not configured.strip():
        configured = os.getenv("NATS_NAMESPACE", "")
    if isinstance(configured, str):
        configured = configured.strip()
        if configured:
            return configured
    return DEFAULT_NATS_NAMESPACE
