from django.conf import settings


def build_nats_trigger_subject(workflow_id: int, node_key: str) -> str:
    """Return the stable, platform-owned subject for one published NATS trigger."""
    namespace = str(getattr(settings, "NATS_NAMESPACE", "bklite") or "bklite").strip(".")
    return f"{namespace}.workflow.{workflow_id}.{node_key}"
