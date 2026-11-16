import json
from pathlib import Path
import runpy
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import query_run

Path = type(Path())


class Locator:
    def __init__(self, text="", click=None):
        self.text = text
        self.on_click = click or (lambda: None)
    def click(self): self.on_click()
    def fill(self, value): pass
    def to_have_count(self, count): assert count == 1
    def to_be_visible(self): pass
    def to_contain_text(self, text): assert text in self.text, (text, self.text)


class RecoveryUiTest(TestCase):
    def run_ui(self, apm_state="已恢复"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/ui-login.json").write_text(json.dumps({"username": "test", "password": "test-only"}))
            (root / "evidence").mkdir()
            current = {"run_id": "run-new", "alerts": {kind: [{"id": kind + str(i)} for i in range(2)] for kind in ["apm", "log"]}}
            page = SimpleNamespace(active=None)
            def role(role_name, **kwargs):
                if role_name == "dialog":
                    return Locator(apm_state if page.active.startswith("apm") else "关闭")
                return Locator()
            page.get_by_role = role
            page.locator = lambda *args: Locator()
            for method in ["goto", "wait_for_url", "wait_for_load_state", "wait_for_timeout", "screenshot"]:
                setattr(page, method, lambda *args, **kwargs: None)
            def row_for(_page, identifier):
                row = Locator("已通知 详情 关闭" if identifier.startswith("apm") else "关闭 已通知 详情")
                row.get_by_role = lambda *args, **kwargs: Locator(click=lambda: setattr(page, "active", identifier))
                return row
            browser = SimpleNamespace(new_context=lambda **kwargs: SimpleNamespace(new_page=lambda: page), close=lambda: None)
            class Playwright:
                def __enter__(self): return SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kwargs: browser))
                def __exit__(self, *args): pass
            module = ModuleType("playwright.sync_api")
            module.sync_playwright = Playwright
            module.expect = lambda locator: locator
            def remap(value): return root if str(value) == "/test" else Path(value)
            with patch.dict(sys.modules, {"playwright": ModuleType("playwright"), "playwright.sync_api": module}), patch("pathlib.Path", side_effect=remap), patch.object(query_run, "verified_run", return_value=current), patch.object(query_run, "find_alert_row", side_effect=row_for):
                runpy.run_path(str(Path(__file__).with_name("query-ui-recovery.py")))
            return json.loads((root / "evidence/query-alert-20261115/ui-recovery-checks.json").read_text())

    def test_apm_status_is_asserted_in_current_detail_not_absent_table_column(self):
        result = self.run_ui()
        self.assertEqual(result["run_id"], "run-new")
        self.assertEqual({item["alert_id"] for item in result["checks"]}, {"apm0", "apm1", "log0", "log1"})

    def test_unrecovered_current_detail_cannot_pass(self):
        with self.assertRaises(AssertionError):
            self.run_ui(apm_state="告警中")
