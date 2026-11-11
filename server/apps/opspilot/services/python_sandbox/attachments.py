"""Server-issued attachment capabilities; no storage credentials enter a sandbox."""
from __future__ import annotations

from datetime import timedelta

from django.core import signing

from apps.opspilot.models import ChatAttachment, WorkflowAttachmentAsset
from apps.opspilot.services.workflow_attachment_service import _ATTACHMENT_DOWNLOAD_URL_RE, WORKFLOW_ATTACHMENT_DOWNLOAD_SALT

ATTACHMENT_GRANT_KEY = "sandbox_attachment_grant"
_GRANT_SALT = "opspilot.sandbox.attachments"
_MAX_FILES = 100


def issue_attachment_grant(*, owner_key, team_id, conversation=None, attachments=()):
    """Call only after the entry point has authenticated the conversation/ uploads."""
    uploaded = list(attachments)
    if conversation is not None:
        scoped = ChatAttachment.objects.filter(
            conversation=conversation,
            owner_key=owner_key,
            team_id=str(team_id),
            status=ChatAttachment.STATUS_READY,
        )
        current = list(scoped.filter(pk__in=[item.pk for item in uploaded])) if uploaded else []
        recent = list(scoped.order_by("-id")[:_MAX_FILES])
        uploaded = list({item.pk: item for item in current + recent}.values())[:_MAX_FILES]
    uploaded_ids = [item.id for item in uploaded if item.owner_key == owner_key and item.team_id == str(team_id)]
    generated = {}
    if conversation is not None:
        # Only server-persisted assistant replies in the authenticated conversation.
        messages = conversation.messages.filter(role="assistant").order_by("-id").values_list("content", flat=True)[:100]
        for content in messages:
            for match in _ATTACHMENT_DOWNLOAD_URL_RE.finditer(content):
                try:
                    payload = signing.loads(match.group(1), salt=WORKFLOW_ATTACHMENT_DOWNLOAD_SALT)
                except signing.BadSignature:
                    continue
                if isinstance(payload, dict) and isinstance(payload.get("aid"), int) and len(generated) < _MAX_FILES:
                    generated[str(payload["aid"])] = payload.get("eid")
    return signing.dumps(
        {
            "uploads": uploaded_ids,
            "generated": generated,
            "owner": owner_key,
            "team": str(team_id),
            "conversation": conversation.pk if conversation is not None else None,
        },
        salt=_GRANT_SALT,
        compress=True,
    )


def attachment_descriptor(asset, *, kind):
    """A short-lived GET capability for one private object, never bucket access."""
    storage = asset.file.storage
    url = storage.client.presigned_get_object(storage.bucket, asset.file.name, expires=timedelta(hours=1))
    return {
        "id": f"{kind}-{asset.pk}",
        "name": asset.original_name if kind == "upload" else asset.filename,
        "size": asset.size if kind == "upload" else None,
        "url": url,
    }


def resolve_attachment_grant(token):
    if not token:
        return []
    payload = signing.loads(token, salt=_GRANT_SALT, max_age=3600)
    # Recheck the uploaded-file ownership and session association at execution time.
    uploads = ChatAttachment.objects.filter(
        pk__in=payload["uploads"],
        owner_key=payload["owner"],
        team_id=payload["team"],
        status=ChatAttachment.STATUS_READY,
    )
    if payload["conversation"] is not None:
        uploads = uploads.filter(conversation_id=payload["conversation"])
    entries = [attachment_descriptor(item, kind="upload") for item in uploads]
    generated = payload["generated"]
    for asset in WorkflowAttachmentAsset.objects.filter(pk__in=generated):
        if asset.execution_id == generated[str(asset.pk)]:
            entries.append(attachment_descriptor(asset, kind="generated"))
    return entries


ATTACHMENT_README = """当前会话授权附件清单：/workspace/attachments/index.json（名称、ID、大小、只读下载地址）。
不必把清单中的下载地址输出给用户。按需读取文件：
python /workspace/attachments/read.py <附件ID>
命令返回已下载文件路径；用 Python 或技能 execute 读取、修改，另存到 /workspace 下。
原始对象只授予 GET 权限；不能覆盖存储中的原附件。
修改后必须调用 generate_attachment_file(filename=新文件名, file_type=类型, sandbox_path=产物路径) 保存新附件。
"""

# Runs inside the container. The manifest is the entire authority available to it.
ATTACHMENT_READER = """import json, pathlib, sys, urllib.request
try:
    entries = json.loads(pathlib.Path('/workspace/attachments/index.json').read_text())
    entry = next(item for item in entries if item['id'] == sys.argv[1])
    target = pathlib.Path('/workspace/attachments/downloads') / entry['id'] / pathlib.PurePosixPath(entry['name'].replace('\\\\', '/')).name
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(entry['url'], timeout=60) as source:
        data = source.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise ValueError('file too large')
    target.write_bytes(data)
    print(str(target))
except Exception:
    sys.stderr.write('附件读取失败：请确认附件 ID、有效期及存储连通性\\n')
    sys.exit(1)
"""
