"""OpsPilot runtime optimization PR2: tasks package contracts."""

from __future__ import annotations

import importlib

import pytest

from apps.opspilot import tasks

pytestmark = pytest.mark.unit

EXPECTED_TASK_NAMES = {
    "chat_flow_celery_task": "apps.opspilot.tasks.chat_flow_celery_task",
    "chat_flow_test_execute_task": "apps.opspilot.tasks.chat_flow_test_execute_task",
    "process_wechat_message": "apps.opspilot.tasks.process_wechat_message",
    "process_dingtalk_message": "apps.opspilot.tasks.process_dingtalk_message",
    "process_wechat_official_message": "apps.opspilot.tasks.process_wechat_official_message",
    "process_enterprise_wechat_aibot_message": "apps.opspilot.tasks.process_enterprise_wechat_aibot_message",
    "process_enterprise_wechat_aibot_reply": "apps.opspilot.tasks.process_enterprise_wechat_aibot_reply",
    "process_skill_channel_im_message": "apps.opspilot.tasks.process_skill_channel_im_message",
    "process_skill_channel_aibot_message": "apps.opspilot.tasks.process_skill_channel_aibot_message",
    "process_skill_channel_aibot_reply": "apps.opspilot.tasks.process_skill_channel_aibot_reply",
    "process_skill_channel_wechat_message": "apps.opspilot.tasks.process_skill_channel_wechat_message",
    "process_skill_channel_wechat_official_message": "apps.opspilot.tasks.process_skill_channel_wechat_official_message",
    "process_skill_channel_dingtalk_message": "apps.opspilot.tasks.process_skill_channel_dingtalk_message",
    "process_memory_write_cache": "apps.opspilot.tasks.process_memory_write_cache",
    "flush_memory_write_cache_for_node": "apps.opspilot.tasks.flush_memory_write_cache_for_node",
    "flush_all_pending_memory_write_cache": "apps.opspilot.tasks.flush_all_pending_memory_write_cache",
    "process_memory_write": "apps.opspilot.tasks.process_memory_write",
    "cleanup_expired_workflow_attachments_task": "apps.opspilot.tasks.cleanup_expired_workflow_attachments_task",
    "wiki_ingest_material_task": "apps.opspilot.tasks.wiki_ingest_material_task",
    "wiki_build_material_task": "apps.opspilot.tasks.wiki_build_material_task",
    "wiki_propose_update_task": "apps.opspilot.tasks.wiki_propose_update_task",
    "wiki_rebuild_kb_task": "apps.opspilot.tasks.wiki_rebuild_kb_task",
    "wiki_process_kb_material_builds_task": "apps.opspilot.tasks.wiki_process_kb_material_builds_task",
    "wiki_batch_ingest_materials_task": "apps.opspilot.tasks.wiki_batch_ingest_materials_task",
    "wiki_retry_markdown_import_task": "apps.opspilot.tasks.wiki_retry_markdown_import_task",
    "wiki_refresh_web_materials_task": "apps.opspilot.tasks.wiki_refresh_web_materials_task",
}

EXPECTED_QUEUES = {
    "chat_flow_celery_task": None,
    "chat_flow_test_execute_task": None,
    "process_wechat_message": "opspilot_channel",
    "process_dingtalk_message": "opspilot_channel",
    "process_wechat_official_message": "opspilot_channel",
    "process_enterprise_wechat_aibot_message": "opspilot_channel",
    "process_enterprise_wechat_aibot_reply": "opspilot_channel",
    "process_skill_channel_im_message": "opspilot_channel",
    "process_skill_channel_aibot_message": "opspilot_channel",
    "process_skill_channel_aibot_reply": "opspilot_channel",
    "process_skill_channel_wechat_message": "opspilot_channel",
    "process_skill_channel_wechat_official_message": "opspilot_channel",
    "process_skill_channel_dingtalk_message": "opspilot_channel",
    "process_memory_write_cache": "opspilot_maintenance",
    "flush_memory_write_cache_for_node": "opspilot_maintenance",
    "flush_all_pending_memory_write_cache": "opspilot_maintenance",
    "process_memory_write": "opspilot_maintenance",
    "cleanup_expired_workflow_attachments_task": "opspilot_maintenance",
    "wiki_ingest_material_task": "opspilot_wiki",
    "wiki_build_material_task": "opspilot_wiki",
    "wiki_propose_update_task": "opspilot_wiki",
    "wiki_rebuild_kb_task": "opspilot_wiki",
    "wiki_process_kb_material_builds_task": "opspilot_wiki",
    "wiki_batch_ingest_materials_task": "opspilot_wiki",
    "wiki_retry_markdown_import_task": "opspilot_wiki",
    "wiki_refresh_web_materials_task": "opspilot_maintenance",
}


class TestTasksPackageExports:
    @pytest.mark.parametrize("attr,expected_name", sorted(EXPECTED_TASK_NAMES.items()))
    def test_task_names_unchanged(self, attr, expected_name):
        assert getattr(tasks, attr).name == expected_name

    @pytest.mark.parametrize("attr,expected_queue", sorted(EXPECTED_QUEUES.items()))
    def test_task_queue_assignments(self, attr, expected_queue):
        task = getattr(tasks, attr)
        actual_queue = getattr(task, "queue", None)
        assert actual_queue == expected_queue

    def test_imports_from_apps_opspilot_tasks_package(self):
        reloaded = importlib.reload(tasks)
        assert reloaded.chat_flow_celery_task.name == "apps.opspilot.tasks.chat_flow_celery_task"
        assert reloaded.process_wechat_message.queue == "opspilot_channel"
        assert reloaded.wiki_build_material_task.queue == "opspilot_wiki"
        assert reloaded.flush_all_pending_memory_write_cache.queue == "opspilot_maintenance"
        assert reloaded.MEMORY_WRITE_PROCESSING_TTL_SECONDS > 0
        assert callable(reloaded._build_memory_write_client)
        assert callable(reloaded._material_pipeline_fingerprints)

    def test_wiki_process_kb_material_builds_task_acks_late(self):
        task = tasks.wiki_process_kb_material_builds_task
        assert task.acks_late is True
        assert task.reject_on_worker_lost is True
        from apps.opspilot import config as ops_config

        schedule = ops_config.CELERY_BEAT_SCHEDULE
        assert schedule["cleanup-expired-workflow-attachments"]["task"] == ("apps.opspilot.tasks.cleanup_expired_workflow_attachments_task")
        assert schedule["wiki-refresh-web-materials"]["task"] == ("apps.opspilot.tasks.wiki_refresh_web_materials_task")

    def test_wiki_process_kb_material_builds_task_ignores_redelivered(self, monkeypatch):
        captured = {}

        def fake_process(kb_id, operator=""):
            captured["kb_id"] = kb_id
            captured["operator"] = operator
            return {"skipped": "runner_active", "processed": 0, "failed": 0}

        monkeypatch.setattr(
            "apps.opspilot.services.wiki.material_build_queue_service.process_kb_material_builds",
            fake_process,
        )
        result = tasks.wiki_process_kb_material_builds_task.run(7, "ops")
        assert captured == {"kb_id": 7, "operator": "ops"}
        assert result["skipped"] == "runner_active"


class TestViewsPackageExports:
    def test_views_module_resolves_package(self):
        import apps.opspilot.views as views

        assert hasattr(views, "execute_chat_flow")
        assert hasattr(views, "execute_skill_channel_chat")
        assert hasattr(views, "submit_approval")
        assert hasattr(views, "get_token_consumption_overview")

    def test_views_submodules_reload_without_cycle(self):
        for module_name in ("chat_flow", "skill_channel", "hitl", "analytics"):
            importlib.import_module(f"apps.opspilot.views.{module_name}")
