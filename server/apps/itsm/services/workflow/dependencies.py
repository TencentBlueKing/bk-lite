"""发布前检查子流程，避免部署成功后才发现调用目标缺失。"""
from apps.itsm.models import Workflow


def validate_subprocesses(design, workflow):
    calls = [node for node in design.get("nodes", []) if node.get("type") in {"call", "subprocess", "subprocess_submit"}]
    keys = {str((node.get("auto") or {}).get("process_key") or "").strip() for node in calls}
    available = set(
        Workflow.objects.filter(
            domain=workflow.domain,
            key__in=keys,
            current_version__is_published=True,
        )
        .exclude(current_version__flowable_deployment_id="")
        .exclude(pk=workflow.pk)
        .values_list("key", flat=True)
    )
    for node in calls:
        key = str((node.get("auto") or {}).get("process_key") or "").strip()
        if not key or key not in available:
            raise ValueError(f"节点「{node.get('name') or node['id']}」引用的子流程未发布或不可用，请先发布子流程")
