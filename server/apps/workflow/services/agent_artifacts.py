from datetime import timedelta
from hashlib import sha256
from pathlib import PurePath

from django.core.files.base import ContentFile
from django.db import transaction

from apps.workflow.models import AtomExecution, ExecutionArtifact, WorkflowExecution
from apps.workflow.services.object_store import MAX_ARTIFACT_DOWNLOAD_BYTES, ArtifactTooLarge, WorkflowObjectStore


def register_agent_artifacts(atom_execution: AtomExecution, *, store=None) -> list[dict]:
    """将本次节点产生的附件移交编排存储，保留独立于智能体临时文件的下载期限。"""
    from apps.opspilot.models import WorkflowAttachmentAsset

    execution = atom_execution.execution
    assets = WorkflowAttachmentAsset.objects.filter(
        execution_id=str(execution.pk),
        flow_id__in=("", str(execution.workflow_id)),
        source_node_id=atom_execution.task_reference,
        created_at__gte=atom_execution.started_at or atom_execution.created_at,
    ).order_by("created_at", "pk")
    if atom_execution.finished_at:
        assets = assets.filter(created_at__lte=atom_execution.finished_at)
    object_store = store or WorkflowObjectStore()
    references = []
    for asset in assets:
        # 工具更新同一个附件时会另存文件。按源文件版本登记，重复执行保留同一引用。
        if not asset.file:
            raise ValueError("智能体生成的附件缺少文件")
        version = sha256(asset.file.name.encode()).hexdigest()
        key = f"workflow/executions/{execution.pk}/agent/{asset.pk}/{version}"
        artifact = ExecutionArtifact.objects.filter(object_key=key).first()
        if artifact is None:
            if asset.file.size > MAX_ARTIFACT_DOWNLOAD_BYTES:
                raise ArtifactTooLarge("智能体附件超过下载大小限制")
            with asset.file.open("rb") as source:
                content = source.read(MAX_ARTIFACT_DOWNLOAD_BYTES + 1)
            if len(content) > MAX_ARTIFACT_DOWNLOAD_BYTES:
                raise ArtifactTooLarge("智能体附件超过下载大小限制")
            retention = timedelta(days=1 if execution.mode == WorkflowExecution.Mode.DEBUG else 30)
            with transaction.atomic():
                artifact, created = ExecutionArtifact.objects.get_or_create(
                    object_key=key,
                    defaults={
                        "execution": execution,
                        "atom_execution": atom_execution,
                        "team": execution.team,
                        "kind": ExecutionArtifact.Kind.AGENT_ATTACHMENT,
                        "format": PurePath(asset.filename).suffix[1:].lower(),
                        "filename": asset.filename,
                        "content_type": asset.mime_type or "application/octet-stream",
                        "size": len(content),
                        "sha256": sha256(content).hexdigest(),
                        "expires_at": asset.created_at + retention,
                        "created_by": "system",
                        "updated_by": "system",
                    },
                )
                if created:
                    object_store.put(key, ContentFile(content, name=asset.filename))
        references.append({"id": str(artifact.pk), "filename": artifact.filename, "format": artifact.format, "size": artifact.size})
    return references
