import pytest


@pytest.mark.django_db
def test_build_record_list_filters_by_material_name(api_client):
    from apps.opspilot.models import BuildRecord, Material, WikiKnowledgeBase

    kb = WikiKnowledgeBase.objects.create(name="kb-build-filter", team=[1], purpose_md="# P", schema_md="# S")
    matched = Material.objects.create(knowledge_base=kb, name="后备电源安全管理指引.docx", material_type="text")
    other = Material.objects.create(knowledge_base=kb, name="无关合同扫描件.pptx", material_type="text")
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        stage="done",
        status="success",
        inputs={"material_id": matched.id, "material_name": matched.name},
    )
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        stage="done",
        status="success",
        inputs={"material_id": other.id, "material_name": other.name},
    )
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        stage="done",
        status="success",
        inputs={"material_id": matched.id},  # 仅 material_id,靠 Material.name 反查
    )

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/build_record/?knowledge_base={kb.id}&material_name=电源")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["count"] == 2
    assert {item["inputs"]["material_id"] for item in data["items"]} == {matched.id}


@pytest.mark.django_db
def test_build_record_list_hides_queue_bookkeeping(api_client):
    from apps.opspilot.models import BuildRecord, Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki.material_build_queue_service import QUEUE_ITEM_TRIGGER, RUNNER_TRIGGER

    kb = WikiKnowledgeBase.objects.create(name="kb-hide-queue", team=[1], purpose_md="# P", schema_md="# S")
    material = Material.objects.create(knowledge_base=kb, name="资料A.docx", material_type="text")
    visible = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material",
        stage="done",
        status="success",
        inputs={"material_id": material.id, "material_name": material.name},
    )
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=QUEUE_ITEM_TRIGGER,
        stage="dispatched",
        status="success",
        inputs={"material_id": material.id, "material_name": material.name},
    )
    BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=RUNNER_TRIGGER,
        stage="done",
        status="success",
        inputs={"kind": "material_build_queue"},
    )

    response = api_client.get(f"/api/v1/opspilot/wiki_mgmt/build_record/?knowledge_base={kb.id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["count"] == 1
    assert data["items"][0]["id"] == visible.id
