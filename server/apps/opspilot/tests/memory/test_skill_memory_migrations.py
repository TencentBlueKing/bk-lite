"""技能记忆 migration：线上已部署合并版 0078，不得再拆成同号历史文件 + 0079。"""

import importlib

from django.db.migrations.operations.fields import AddField
from django.db.migrations.operations.models import AddConstraint
from django.db.migrations.operations.special import RunPython

Migration0078 = importlib.import_module("apps.opspilot.migrations.0078_force_wiki_and_skill_memory").Migration


def _add_field_names(migration):
    return {(op.model_name, op.name) for op in migration.operations if isinstance(op, AddField)}


def test_combined_0078_adds_force_wiki_and_skill_memory_fields():
    assert Migration0078.dependencies == [
        ("opspilot", "0077_alter_llmskill_show_think"),
        ("system_mgmt", "0039_user_user_id"),
    ]
    assert _add_field_names(Migration0078) == {
        ("llmskill", "force_wiki_grounded"),
        ("llmskill", "memory_space"),
        ("llmskill", "memory_write_rounds"),
        ("skillconversation", "memory_written_message_id"),
        ("memoryspace", "is_builtin"),
        ("memory", "owner_user_id"),
    }
    assert any(
        isinstance(op, AddConstraint) and getattr(op.constraint, "name", None) == "uniq_builtin_memory_space" for op in Migration0078.operations
    )
    assert any(isinstance(op, RunPython) and op.code.__name__ == "backfill_memory_owner_user_id" for op in Migration0078.operations)
