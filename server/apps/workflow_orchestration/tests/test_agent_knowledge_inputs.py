import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.workflow_orchestration.services.agent_knowledge_inputs import resolve_uploaded_agent_knowledge, store_uploaded_agent_knowledge


class MemoryStore:
    def __init__(self):
        self.objects = {}

    def put(self, key, content):
        self.objects[key] = content.read()

    def get(self, key):
        content = self.objects[key]
        return content, key.rsplit("/", 1)[-1], len(content)


def test_agent_knowledge_upload_returns_scoped_reference_and_resolves_utf8_content():
    store = MemoryStore()
    reference = store_uploaded_agent_knowledge(
        SimpleUploadedFile("巡检知识.md", "# 排障\n先检查磁盘。".encode()),
        workflow_id=12,
        team=7,
        store=store,
    )

    resolved = resolve_uploaded_agent_knowledge([reference], workflow_id="12", team=7, store=store)

    assert reference["kind"] == "workflow_agent_knowledge"
    assert reference["name"] == "巡检知识.md"
    assert resolved == [{"name": "巡检知识.md", "content": "# 排障\n先检查磁盘。"}]


def test_agent_knowledge_reference_cannot_cross_workflow_or_organization():
    store = MemoryStore()
    reference = store_uploaded_agent_knowledge(
        SimpleUploadedFile("knowledge.md", b"safe content"),
        workflow_id=12,
        team=7,
        store=store,
    )

    with pytest.raises(ValueError, match="引用内容非法"):
        resolve_uploaded_agent_knowledge([reference], workflow_id=13, team=7, store=store)
    with pytest.raises(ValueError, match="引用内容非法"):
        resolve_uploaded_agent_knowledge([reference], workflow_id=12, team=8, store=store)


@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("knowledge.txt", b"text", "文件类型不受支持"),
        ("knowledge.md", b"", "不能为空"),
        ("knowledge.md", b"\xff", "UTF-8"),
    ],
)
def test_agent_knowledge_upload_rejects_invalid_files(filename, content, message):
    with pytest.raises(ValueError, match=message):
        store_uploaded_agent_knowledge(
            SimpleUploadedFile(filename, content),
            workflow_id=12,
            team=7,
            store=MemoryStore(),
        )
