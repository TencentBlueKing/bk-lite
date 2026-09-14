"""技能记忆 migration 链回归：历史 0078 不得被同号重写。"""

import importlib

from django.db.migrations.operations.fields import AddField
from django.db.migrations.operations.models import AddConstraint
from django.db.migrations.operations.special import RunPython

Migration0078 = importlib.import_module("apps.opspilot.migrations.0078_llmskill_force_wiki_grounded").Migration
Migration0079 = importlib.import_module("apps.opspilot.migrations.0079_skill_memory").Migration


def _add_field_names(migration):
    return {(op.model_name, op.name) for op in migration.operations if isinstance(op, AddField)}


def test_historical_0078_only_adds_force_wiki_grounded():
    assert Migration0078.dependencies == [("opspilot", "0077_alter_llmskill_show_think")]
    assert _add_field_names(Migration0078) == {("llmskill", "force_wiki_grounded")}
    assert not any(isinstance(op, RunPython) for op in Migration0078.operations)


def test_0079_adds_skill_memory_fields_without_readding_force_wiki():
    assert ("opspilot", "0078_llmskill_force_wiki_grounded") in Migration0079.dependencies
    assert ("system_mgmt", "0039_user_user_id") in Migration0079.dependencies
    added = _add_field_names(Migration0079)
    assert ("llmskill", "force_wiki_grounded") not in added
    assert added == {
        ("llmskill", "memory_space"),
        ("llmskill", "memory_write_rounds"),
        ("skillconversation", "memory_written_message_id"),
        ("memoryspace", "is_builtin"),
        ("memory", "owner_user_id"),
    }
    assert any(
        isinstance(op, AddConstraint) and getattr(op.constraint, "name", None) == "uniq_builtin_memory_space"
        for op in Migration0079.operations
    )
    assert any(isinstance(op, RunPython) and op.code.__name__ == "backfill_memory_owner_user_id" for op in Migration0079.operations)
