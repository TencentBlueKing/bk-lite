"""Execute extracted pure CMDB branches only; no actor, framework, DB or HTTP."""
import ast
import copy
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[4]


def source_tree(relative):
    return ast.parse((SERVER / relative).read_text())


def compile_nodes(nodes, namespace=None):
    namespace = {} if namespace is None else dict(namespace)
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, "<production-pure-branches>", "exec"), namespace)
    return namespace


def method(tree, name):
    node = copy.deepcopy(next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name))
    node.decorator_list = []
    return node


class CmdbModulePermissionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = source_tree("apps/cmdb/utils/permission_util.py")
        formatter = method(tree, "format_user_context_permissions")
        branch = copy.deepcopy(
            next(node for node in formatter.body if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "privilege")
        )
        # Omit only the external organization lookup; teams are scalar IDs here.
        lookup = branch.body.pop(0)
        assert isinstance(lookup, ast.Assign) and lookup.targets[0].id == "teams"
        wrapper = ast.parse("def module_result(privilege, teams):\n    pass").body[0]
        wrapper.body = [branch, ast.Return(value=ast.Constant(value=None))]
        cls.module_result = staticmethod(compile_nodes([wrapper])["module_result"])

        constants = source_tree("apps/cmdb/constants/constants.py")
        values = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in constants.body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {"VIEW", "OPERATE"}
        }
        cls.view, cls.operate = values["VIEW"], values["OPERATE"]
        pure = method(tree, "format_organizations_instances_map")
        cls.convert = staticmethod(compile_nodes([pure], values)[pure.name])

        scope = source_tree("apps/core/utils/module_scope.py")
        bindings = [
            copy.deepcopy(node)
            for node in scope.body
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in {"MODULE_ADMIN_ROLE", "MODULE_AUDITOR_ROLE", "EXCLUDED_CLIENTS"}
        ]
        cls.privilege = staticmethod(compile_nodes(bindings + [method(scope, "module_privilege")])["module_privilege"])

        cls.consumer_reads = []
        for relative, variable in [
            ("apps/cmdb/services/model.py", "organization_permission_data"),
            ("apps/cmdb/services/instance.py", "organization_permission_data"),
            ("apps/cmdb/views/model.py", "default_group_id_permission"),
            ("apps/cmdb/services/transfer_authorization.py", "value"),
        ]:
            node = next(
                node
                for node in ast.walk(source_tree(relative))
                if isinstance(node, ast.Subscript)
                and isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Name)
                and node.value.id == variable
                and isinstance(node.slice, ast.Constant)
                and node.slice.value == "inst_names"
            )
            cls.consumer_reads.append((variable, compile(ast.Expression(body=node), relative, "eval")))

    def auditor_map(self):
        return self.module_result(self.privilege(["cmdb--module_auditor"], "cmdb"), [2, "3"])

    def test_auditor_contract_supplies_required_instance_names(self):
        result = self.auditor_map()
        self.assertEqual(set(result), {2, 3})
        for row in result.values():
            self.assertEqual(row["inst_names"], [])
            self.assertEqual(row["permission_instances_map"], {})
            self.assertIs(row["__default_model"], True)

    def test_real_consumers_direct_key_reads_accept_auditor_rows(self):
        for row in self.auditor_map().values():
            for variable, expression in self.consumer_reads:
                with self.subTest(consumer=expression.co_filename):
                    self.assertEqual(eval(expression, {}, {variable: row}), [])

    def test_default_marker_keeps_every_auditor_organization_read_only(self):
        for organization, row in self.convert(self.auditor_map()).items():
            self.assertEqual(row["permission"], {self.view})
            self.assertEqual(row["organization_permission_map"], {organization: {self.view}})
            self.assertNotIn(self.operate, row["permission"])

    def test_platform_auditor_with_module_admin_stays_read_only(self):
        privilege = self.privilege(["cmdb--module_admin"], "cmdb", platform_auditor=True)
        self.assertEqual(privilege, "auditor")
        result = self.module_result(privilege, [2])
        self.assertEqual(result[2]["inst_names"], [])
        self.assertEqual(self.convert(result)[2]["permission"], {self.view})

    def test_module_admin_contract_and_operations_are_unchanged(self):
        result = self.module_result(self.privilege(["cmdb--module_admin"], "cmdb"), [2])
        self.assertEqual(result, {2: {"permission_instances_map": {}, "inst_names": []}})
        self.assertEqual(self.convert(result)[2]["permission"], {self.view, self.operate})

    def test_ordinary_and_cross_app_roles_skip_module_short_circuit(self):
        for roles, app in [
            (["cmdb--viewer"], "cmdb"),
            (["log--module_auditor"], "cmdb"),
            (["cmdb--module_auditor"], "log"),
            (["cmdb--module_admin"], "system-manager"),
        ]:
            with self.subTest(roles=roles, app=app):
                privilege = self.privilege(roles, app)
                self.assertIsNone(privilege)
                self.assertIsNone(self.module_result(privilege, [2]))

    def test_empty_authorized_teams_stays_empty(self):
        for privilege in ("admin", "auditor"):
            self.assertEqual(self.module_result(privilege, []), {})

    def test_each_organization_has_an_independent_instance_names_list(self):
        result = self.auditor_map()
        result[2]["inst_names"].append("test-model")
        self.assertEqual(result[3]["inst_names"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
