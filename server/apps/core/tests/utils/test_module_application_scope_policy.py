"""Scalar policy regressions, no user/request/ORM/HTTP or database setup."""
import ast
import unittest
from pathlib import Path

from apps.core.utils.module_scope import module_privilege


class ModuleApplicationScopePolicyTests(unittest.TestCase):
    def test_admin_scope_only_matches_its_application(self):
        for app in ("job", "patch", "mlops", "alarm", "opspilot"):
            with self.subTest(app=app):
                self.assertEqual(module_privilege([f"{app}--module_admin"], app), "admin")
                self.assertIsNone(module_privilege(["monitor--module_admin"], app))

    def test_auditor_scope_never_becomes_admin_from_ordinary_write_role(self):
        for app in ("job", "patch", "mlops", "alarm", "opspilot"):
            self.assertEqual(module_privilege([f"{app}--module_auditor", f"{app}--admin"], app), "auditor")

    def test_platform_auditor_keeps_module_admin_readonly(self):
        for app in ("job", "patch", "mlops", "alarm", "opspilot"):
            self.assertEqual(module_privilege([f"{app}--module_admin"], app, platform_auditor=True), "auditor")

    def test_ordinary_scope_remains_ordinary_even_with_auditor_flag(self):
        for names in ([], ["job--admin"], ["mlops--normal"]):
            self.assertIsNone(module_privilege(names, "job", platform_auditor=True))

    def test_excluded_apps_never_gain_module_scope(self):
        for app in ("", "system-manager", "ops-console"):
            self.assertIsNone(module_privilege([f"{app}--module_admin"], app, platform_auditor=True))


class ApplicationScopeGateTests(unittest.TestCase):
    """Evaluate actual source branch expressions using scalars, never identity objects.

    These are narrow source-extracted policy checks, not ORM/dispatch tests.
    """

    ROOT = Path(__file__).resolve().parents[4]

    def gate(self, relative, function, *, app, names=(), admin=False, auditor=False, operation="View", variables=None, last=False):
        tree = ast.parse((self.ROOT / relative).read_text())
        func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function)
        conditions = [
            n.test
            for n in ast.walk(func)
            if isinstance(n, ast.If)
            and any(
                isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "effective_module_privilege"
                for call in ast.walk(n.test)
            )
            or isinstance(n, ast.If)
            and any(isinstance(name, ast.Name) and name.id == "module_scope" for name in ast.walk(n.test))
        ]
        expression = conditions[-1] if last else conditions[0]
        privilege = module_privilege(names, app, platform_auditor=auditor and not admin)

        class Scalars(ast.NodeTransformer):
            def visit_Call(self, node):
                if isinstance(node.func, ast.Name) and node.func.id == "effective_module_privilege":
                    self_outer.assertEqual(ast.literal_eval(node.args[1]), app)
                    return ast.copy_location(ast.Name(id="_module_privilege", ctx=ast.Load()), node)
                if isinstance(node.func, ast.Name) and node.func.id == "getattr" and ast.literal_eval(node.args[1]) == "is_superuser":
                    return ast.copy_location(ast.Constant(admin), node)
                raise AssertionError("Unexpected non-scalar policy dependency")

        self_outer = self
        expression = Scalars().visit(expression)
        return bool(
            eval(
                compile(ast.fix_missing_locations(ast.Expression(expression)), "<source gate>", "eval"),
                {"__builtins__": {}},
                {"operation": operation, "_module_privilege": privilege, "module_scope": privilege, **(variables or {})},
            )
        )

    def test_job_execution_bypass_is_write_admin_only(self):
        args = ("apps/job_mgmt/views/execution.py", "_get_authorized_team_ids")
        self.assertTrue(self.gate(*args, app="job", names=["job--module_admin"]))
        for names, auditor in [
            (["job--module_auditor", "job--admin"], False),
            (["job--module_admin"], True),
            (["node--module_admin"], False),
            ([], False),
        ]:
            self.assertFalse(self.gate(*args, app="job", names=names, auditor=auditor))

    def test_patch_org_membership_bypass_is_current_app_only(self):
        args = ("apps/patch_mgmt/services/target_access.py", "_validate_current_team")
        for role in ["module_admin", "module_auditor"]:
            self.assertTrue(self.gate(*args, app="patch", names=[f"patch--{role}"]))
        self.assertFalse(self.gate(*args, app="patch", names=["job--module_admin"]))
        self.assertFalse(self.gate(*args, app="patch"))

    def test_patch_operable_root_stays_empty_for_readonly_module_scope(self):
        args = ("apps/patch_mgmt/services/target_access.py", "queryset")
        self.assertTrue(self.gate(*args, app="patch", names=["patch--module_auditor", "patch--admin"], operation="Operate"))
        self.assertTrue(self.gate(*args, app="patch", names=["patch--module_admin"], auditor=True, operation="Operate"))
        self.assertFalse(self.gate(*args, app="patch", names=["patch--module_auditor"], operation="View"))
        self.assertFalse(self.gate(*args, app="patch", names=["patch--module_admin"], operation="Operate"))
        self.assertFalse(self.gate(*args, app="patch", names=["patch--module_auditor"], admin=True, operation="Operate"))

    def test_mlops_root_assignment_scope_never_expands_for_readonly_module(self):
        args = ("apps/mlops/utils/group_scope.py", "get_allowed_team_ids")
        self.assertTrue(self.gate(*args, app="mlops", names=["mlops--module_admin"]))
        self.assertFalse(self.gate(*args, app="mlops", names=["mlops--module_auditor"]))
        self.assertFalse(self.gate(*args, app="mlops", names=["mlops--module_admin"], auditor=True))
        self.assertFalse(self.gate(*args, app="mlops", names=["job--module_admin"]))

    def test_vendor_membership_remains_required_outside_its_module(self):
        args = ("apps/opspilot/utils/vendor_model_mixin.py", "by_vendor")
        self.assertFalse(self.gate(*args, app="opspilot", names=["opspilot--module_admin"]))
        self.assertFalse(self.gate(*args, app="opspilot", names=["opspilot--module_auditor"]))
        self.assertTrue(self.gate(*args, app="opspilot", names=["job--module_admin"]))
        self.assertTrue(self.gate(*args, app="opspilot"))

    def test_alarm_membership_expands_only_for_its_module(self):
        args = ("apps/alerts/utils/permission_scope.py", "get_query_group_ids")
        self.assertFalse(self.gate(*args, app="alarm", names=["alarm--module_auditor"]))
        self.assertFalse(self.gate(*args, app="alarm", names=["alarm--module_admin"]))
        self.assertTrue(self.gate(*args, app="alarm", names=["job--module_admin"]))
        self.assertTrue(self.gate(*args, app="alarm"))

    def test_mlops_child_team_guard_retains_parent_filter_and_ordinary_scope(self):
        args = ("apps/mlops/utils/group_scope.py", "filter_queryset_by_parent_team")
        variables = {"current_team": 9, "allowed_team_ids": {1}}
        self.assertFalse(self.gate(*args, app="mlops", names=["mlops--module_auditor"], variables=variables))
        self.assertFalse(self.gate(*args, app="mlops", names=["mlops--module_admin"], variables={"current_team": 9, "allowed_team_ids": None}))
        self.assertTrue(self.gate(*args, app="mlops", variables=variables))
        self.assertTrue(self.gate(*args, app="mlops", names=["mlops--module_admin"], variables={"current_team": 0, "allowed_team_ids": None}))
        tree = ast.parse((self.ROOT / args[0]).read_text())
        func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == args[1])
        self.assertIn("parent_team_lookup", ast.unparse(func.body[-1]))
        self.assertIn("current_team", ast.unparse(func.body[-1]))

    def test_alarm_secret_mutation_is_blocked_before_any_team_or_orm_access(self):
        args = ("apps/alerts/service/alert_source_credential.py", "_mutate")
        self.assertTrue(self.gate(*args, app="alarm", names=["alarm--module_auditor", "alarm--admin"]))
        self.assertTrue(self.gate(*args, app="alarm", names=["alarm--module_admin"], auditor=True))
        self.assertFalse(self.gate(*args, app="alarm", names=["alarm--module_admin"]))
        self.assertFalse(self.gate(*args, app="alarm"))
        self.assertFalse(self.gate(*args, app="alarm", names=["alarm--module_auditor"], admin=True))
        tree = ast.parse((self.ROOT / args[0]).read_text())
        func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == args[1])
        self.assertIsInstance(func.body[0], ast.If)
        self.assertIsInstance(func.body[0].body[0], ast.Raise)

    def test_apm_current_scope_accepts_module_auditor_but_assignment_does_not(self):
        args = ("apps/apm/services/access.py", "current_organization_id")
        self.assertTrue(self.gate(*args, app="apm", names=["apm--module_auditor"]))
        self.assertFalse(self.gate(*args, app="apm", names=["rum--module_admin"]))
        for function in ["assignable_organization_ids", "validate_assignable_organizations"]:
            args = ("apps/apm/services/access.py", function)
            self.assertTrue(self.gate(*args, app="apm", names=["apm--module_admin"]))
            self.assertFalse(self.gate(*args, app="apm", names=["apm--module_admin"], auditor=True))
            self.assertFalse(self.gate(*args, app="apm", names=["apm--module_auditor"]))
            self.assertFalse(self.gate(*args, app="apm"))

    def test_apm_rum_notification_wire_context_names_its_own_app(self):
        for file, function, app in [
            ("apps/apm/views/control_plane.py", "_notification_actor_context", "apm"),
            ("apps/rum/views/monitors.py", "_actor_context", "rum"),
        ]:
            tree = ast.parse((self.ROOT / file).read_text())
            func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function)
            result = next(n.value for n in ast.walk(func) if isinstance(n, ast.Return))
            fields = {ast.literal_eval(k): v for k, v in zip(result.keys, result.values)}
            self.assertEqual(ast.literal_eval(fields["app"]), app)
            self.assertIn("group_list", fields)
            self.assertIn("current_team", fields)


if __name__ == "__main__":
    unittest.main()
