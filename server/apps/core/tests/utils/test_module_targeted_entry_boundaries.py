"""Scalar/source-branch checks only: no request, actor, ORM, RPC or DRF dispatch."""
import ast
import hashlib
import unittest
from pathlib import Path

from apps.core.utils.module_scope import module_privilege

ROOT = Path(__file__).resolve().parents[4]
LOG = "apps/log/views/collect_config.py"
CMDB = "apps/cmdb/views/custom_reporting.py"
OA = "apps/operation_analysis/services/import_export/authorization_service.py"
LOG_WRITES = {"batch_create", "remove_collect_instance", "clear_removed_collector", "reassign_collector_node", "instance_update", "set_organizations"}
CMDB_WRITES = {"create", "update", "destroy", "issue_credential", "rotate_credential", "revoke_credential", "approve_review", "reject_review"}


def class_method(file, cls_name, method_name):
    tree = ast.parse((ROOT / file).read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name)
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    return cls, method


class ModuleTargetedEntryBoundariesTests(unittest.TestCase):
    def predicate(self, file, cls_name, app, expected_actions):
        _, method = class_method(file, cls_name, "initial")
        self.assertEqual(ast.unparse(method.body[0]), "super().initial(request, *args, **kwargs)")
        self.assertIsInstance(method.body[1], ast.If)
        self.assertIsInstance(method.body[1].body[0], ast.Raise)
        expression = method.body[1].test
        membership = next(n for n in ast.walk(expression) if isinstance(n, ast.Compare) and any(isinstance(op, ast.In) for op in n.ops))
        self.assertEqual(set(ast.literal_eval(membership.comparators[0])), expected_actions)
        outer = self

        class Scalars(ast.NodeTransformer):
            def visit_Call(self, node):
                if isinstance(node.func, ast.Name) and node.func.id == "effective_module_privilege":
                    outer.assertEqual(ast.literal_eval(node.args[1]), app)
                    return ast.copy_location(ast.Name(id="privilege", ctx=ast.Load()), node)
                if isinstance(node.func, ast.Name) and node.func.id == "getattr":
                    outer.assertEqual(ast.literal_eval(node.args[1]), "is_superuser")
                    return ast.copy_location(ast.Name(id="platform_admin", ctx=ast.Load()), node)
                raise AssertionError("Unexpected non-scalar dependency")

            def visit_Attribute(self, node):
                outer.assertEqual(ast.unparse(node), "self.action")
                return ast.copy_location(ast.Name(id="action", ctx=ast.Load()), node)

        expression = Scalars().visit(expression)
        return compile(ast.fix_missing_locations(ast.Expression(expression)), "<entry predicate>", "eval")

    def assert_policy(self, file, cls_name, app, actions):
        predicate = self.predicate(file, cls_name, app, actions)
        cases = [
            ([f"{app}--module_auditor", f"{app}--admin"], False, False, True),
            ([f"{app}--module_admin"], False, True, True),
            ([f"{app}--module_admin"], False, False, False),
            (["monitor--module_auditor"], False, False, False),
            ([f"{app}--admin"], False, False, False),
            ([], False, True, False),
            ([f"{app}--module_auditor"], True, False, False),
        ]
        for action in actions:
            for names, admin, auditor, expected in cases:
                with self.subTest(app=app, action=action, names=names, admin=admin, auditor=auditor):
                    privilege = module_privilege(names, app, platform_auditor=auditor and not admin)
                    actual = eval(predicate, {"__builtins__": {}}, {"privilege": privilege, "platform_admin": admin, "action": action})
                    self.assertEqual(actual, expected)

    def test_log_six_write_actions_reject_effective_module_auditors(self):
        self.assert_policy(LOG, "CollectInstanceViewSet", "log", LOG_WRITES)

    def test_log_post_search_and_metadata_remain_outside_write_gate(self):
        predicate = self.predicate(LOG, "CollectInstanceViewSet", "log", LOG_WRITES)
        for action in ["search", "metadata", None]:
            self.assertFalse(eval(predicate, {"__builtins__": {}}, {"privilege": "auditor", "platform_admin": False, "action": action}))

    def test_log_configuration_write_rejects_effective_module_auditors(self):
        self.assert_policy(LOG, "CollectConfigViewSet", "log", {"update_instance_collect_config"})

    def test_log_configuration_post_read_stays_outside_write_gate(self):
        predicate = self.predicate(LOG, "CollectConfigViewSet", "log", {"update_instance_collect_config"})
        for action in ["get_config_content", "metadata", None]:
            self.assertFalse(eval(predicate, {"__builtins__": {}}, {"privilege": "auditor", "platform_admin": False, "action": action}))

    def test_log_configuration_action_inventory_distinguishes_post_read_from_write(self):
        cls, _ = class_method(LOG, "CollectConfigViewSet", "get_config_content")
        actions = {}
        for method in cls.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            for decorator in method.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name) and decorator.func.id == "action":
                    actions[method.name] = next(ast.literal_eval(k.value) for k in decorator.keywords if k.arg == "methods")
        self.assertEqual(actions, {"get_config_content": ["post"], "update_instance_collect_config": ["post"]})

    def test_cmdb_eight_management_mutations_reject_effective_module_auditors(self):
        self.assert_policy(CMDB, "CustomReportingTaskViewSet", "cmdb", CMDB_WRITES)

    def test_cmdb_reads_and_separate_public_token_ingest_are_untouched(self):
        predicate = self.predicate(CMDB, "CustomReportingTaskViewSet", "cmdb", CMDB_WRITES)
        for action in ["list", "retrieve", "stats", "field_registrations", "batch_activity", "onboarding_document", "metadata"]:
            self.assertFalse(eval(predicate, {"__builtins__": {}}, {"privilege": "auditor", "platform_admin": False, "action": action}))
        tree = ast.parse((ROOT / CMDB).read_text())
        ingest = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CustomReportingIngestViewSet")
        self.assertFalse(any(isinstance(n, ast.FunctionDef) and n.name == "initial" for n in ingest.body))
        self.assertEqual(ast.unparse(ingest.bases[0]), "OpenAPIViewSet")

    def test_oa_only_module_admin_selects_real_current_team_descendants(self):
        _, method = class_method(OA, "ImportExportAuthorizationService", "_get_export_group_ids")
        self.assertEqual(ast.unparse(method.body[0].test), "current_team is None")
        self.assertEqual(ast.unparse(method.body[1].body[0]), "return [current_team]")
        gate = method.body[2]
        self.assertEqual(ast.literal_eval(gate.test.left.args[1]), "ops-analysis")
        self.assertEqual(ast.unparse(gate.body[-1]), "return GroupUtils.get_group_with_descendants(current_team)")
        for names, auditor, expected in [
            (["ops-analysis--module_admin"], False, True),
            (["ops-analysis--module_admin"], True, False),
            (["ops-analysis--module_auditor"], False, False),
            (["log--module_admin"], False, False),
            ([], False, False),
        ]:
            self.assertEqual(module_privilege(names, "ops-analysis", platform_auditor=auditor) == "admin", expected)

    def test_only_initial_guards_and_oa_descendant_branch_changed(self):
        cases = [
            (LOG, "CollectInstanceViewSet", "74733ac088953430a3ed26d09b634748407226f3e0c83947df63ac2d45909fa9"),
            (CMDB, "CustomReportingTaskViewSet", "06a83cdcb28706a0a5adae534b3c1de0887905ddd174c2cc4c701c3695c74b17"),
            (OA, "ImportExportAuthorizationService", "f3cf1ac84e09403f3f1e38e2f09d0131a089f98fff0dd1073abda3fa75f27ab3"),
        ]
        for file, cls, original in cases:
            _, method = class_method(file, cls, "_get_export_group_ids" if file == OA else "initial")
            target = method.body[2] if file == OA else method
            lines = (ROOT / file).read_text().splitlines(True)
            targets = [target]
            if file == LOG:
                tree = ast.parse("".join(lines))
                config_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CollectConfigViewSet")
                targets.extend(n for n in config_class.body if isinstance(n, ast.FunctionDef) and n.name == "initial")
            for inserted in sorted(targets, key=lambda n: n.lineno, reverse=True):
                self.assertEqual(lines[inserted.end_lineno], "\n")
                del lines[inserted.lineno - 1 : inserted.end_lineno + 1]
            text = "".join(lines)
            if file != OA:
                text = text.replace("from apps.core.utils.module_scope import effective_module_privilege\n", "", 1).replace(
                    "from rest_framework.exceptions import PermissionDenied\n", "", 1
                )
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), original, file)


if __name__ == "__main__":
    unittest.main()
