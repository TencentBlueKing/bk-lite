"""Wiki Celery 任务测试:用 .apply() 同步执行(无需 broker)。"""

import pytest


def _kb(schema="# s"):
    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.create(name="kb", team=[1], schema_md=schema)


def _material(kb):
    from apps.opspilot.models import Material

    return Material.objects.create(knowledge_base=kb, name="m", material_type="text", text_content="facts")


@pytest.mark.django_db
def test_build_task_creates_build_record():
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.tasks import wiki_build_material_task

    kb = _kb()
    mat = _material(kb)
    # 无 llm_model -> 生成 0 页,但构建记录应成功落库
    rid = wiki_build_material_task.apply(args=[mat.id]).get()
    assert rid is not None
    rec = BuildRecord.objects.get(id=rid)
    assert rec.trigger == "material" and rec.status == "success"


@pytest.mark.django_db
def test_build_task_missing_material_returns_none():
    from apps.opspilot.tasks import wiki_build_material_task

    assert wiki_build_material_task.apply(args=[999999]).get() is None


@pytest.mark.django_db
def test_rebuild_task_creates_record():
    from apps.opspilot.models import BuildRecord
    from apps.opspilot.tasks import wiki_rebuild_kb_task

    kb = _kb()
    rid = wiki_rebuild_kb_task.apply(args=[kb.id]).get()
    assert BuildRecord.objects.filter(id=rid, trigger="rebuild", status="success").exists()


@pytest.mark.django_db
def test_propose_update_task_missing_returns_none():
    from apps.opspilot.tasks import wiki_propose_update_task

    assert wiki_propose_update_task.apply(args=[999999]).get() is None
