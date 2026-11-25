"""Scalar policy and source-boundary checks only; no identity, ORM or HTTP execution."""
import ast
import hashlib
import unittest
from pathlib import Path

from apps.core.utils.module_scope import module_privilege

SOURCE = Path(__file__).resolve().parents[4] / "apps/operation_analysis/services/import_export/authorization_service.py"
BASE_SHA256 = "2ec55a19d5db186cfabd4a36fad87e55e587bf13580990ec36653e397b586d3e"


class OpsAnalysisImportScopeTests(unittest.TestCase):
    def source_parts(self):
        tree = ast.parse(SOURCE.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ImportExportAuthorizationService")
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "validate_current_team")
        return cls, method

    def test_actual_added_predicate_uses_current_app_admin_not_auditor(self):
        cls, method = self.source_parts()
        app = next(
            ast.literal_eval(n.value)
            for n in cls.body
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "APP_PERMISSION_NAME" for t in n.targets)
        )
        self.assertEqual(app, "ops-analysis")
        gate = next(
            n.test
            for n in method.body
            if isinstance(n, ast.If)
            and isinstance(n.test, ast.Compare)
            and isinstance(n.test.left, ast.Call)
            and isinstance(n.test.left.func, ast.Name)
            and n.test.left.func.id == "effective_module_privilege"
        )
        self.assertEqual(ast.unparse(gate.left.args[1]), "cls.APP_PERMISSION_NAME")
        gate.left = ast.Name(id="privilege", ctx=ast.Load())
        predicate = compile(ast.fix_missing_locations(ast.Expression(gate)), "<import scope predicate>", "eval")
        cases = [
            (["ops-analysis--module_admin"], False, True),
            (["ops-analysis--module_admin"], True, False),
            (["ops-analysis--module_auditor", "ops-analysis--admin"], False, False),
            (["monitor--module_admin"], False, False),
            (["ops-analysis--admin"], False, False),
            ([], False, False),
        ]
        for names, auditor, expected in cases:
            with self.subTest(names=names, auditor=auditor):
                privilege = module_privilege(names, app, platform_auditor=auditor)
                self.assertEqual(eval(predicate, {"__builtins__": {}}, {"privilege": privilege}), expected)

    def test_missing_team_rejection_remains_before_module_bypass(self):
        _, method = self.source_parts()
        self.assertEqual(ast.unparse(method.body[1].test), "not current_team")
        self.assertIsInstance(method.body[1].body[0], ast.Raise)
        self.assertIn("effective_module_privilege", ast.unparse(method.body[2].test))
        self.assertEqual(ast.unparse(method.body[2].body[0]), "return current_team")

    def test_only_import_and_org_gate_change_all_object_permissions_preserved(self):
        text = SOURCE.read_text()
        text = text.replace("from apps.core.utils.module_scope import effective_module_privilege\n", "", 1)
        addition = '        if effective_module_privilege(request.user, cls.APP_PERMISSION_NAME) == "admin":\n            return current_team\n\n'
        self.assertEqual(text.count(addition), 1)
        text = text.replace(addition, "", 1)
        descendants = (
            '        if effective_module_privilege(request.user, "ops-analysis") == "admin":\n'
            "            from apps.system_mgmt.utils.group_utils import GroupUtils\n\n"
            "            return GroupUtils.get_group_with_descendants(current_team)\n\n"
        )
        text = text.replace(descendants, "", 1)
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), BASE_SHA256)


if __name__ == "__main__":
    unittest.main()
