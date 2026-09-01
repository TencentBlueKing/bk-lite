"""init_display_fields：dry-run 提示；成功/失败结果输出。"""
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_init_display_fields_dry_run_success(monkeypatch, capsys):
    init = MagicMock()
    init.initialize_all.return_value = {
        "success": True,
        "models_processed": 2,
        "instances_processed": 5,
        "errors": [],
    }
    monkeypatch.setattr(
        "apps.cmdb.management.commands.init_display_fields.DisplayFieldInitializer",
        lambda: init,
    )
    call_command("init_display_fields", dry_run=True)
    out = capsys.readouterr().out
    assert "试运行" in out
    assert "初始化完成" in out
    assert "模型数: 2" in out
    init.initialize_all.assert_called_once()


def test_init_display_fields_prints_errors(monkeypatch, capsys):
    init = MagicMock()
    init.initialize_all.return_value = {
        "success": False,
        "models_processed": 1,
        "instances_processed": 0,
        "errors": ["graph down"],
    }
    monkeypatch.setattr(
        "apps.cmdb.management.commands.init_display_fields.DisplayFieldInitializer",
        lambda: init,
    )
    call_command("init_display_fields")
    out = capsys.readouterr().out
    assert "初始化失败" in out
    assert "graph down" in out
