"""Database-free checks of the default-write rejection boundary.

Run directly with Python to avoid Django/pytest application fixtures. Only the
four boundary methods are loaded from source; application imports and ORM class
attributes are deliberately not evaluated. This is not an authenticated API test.
"""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from rest_framework.exceptions import MethodNotAllowed


class RoleDefaultWriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from django.conf import settings

        if not settings.configured:
            settings.configure(USE_I18N=False)
        path = Path(__file__).resolve().parents[1] / "viewset" / "role_viewset.py"
        tree = ast.parse(path.read_text(), filename=str(path))
        role = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "RoleViewSet")
        methods = {"create", "update", "partial_update", "destroy"}
        boundary = ast.Module(
            body=[node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "rest_framework.exceptions"]
            + [node for node in role.body if isinstance(node, ast.FunctionDef) and node.name in methods],
            type_ignores=[],
        )
        cls.boundary = {}
        exec(compile(boundary, str(path), "exec"), cls.boundary)

    def assert_rejected(self, action, method):
        self.assertTrue(action in self.boundary, "Default write must not fall through to ModelViewSet")
        with self.assertRaises(MethodNotAllowed) as caught:
            self.boundary[action](object(), SimpleNamespace(method=method), pk="unused")
        self.assertEqual(caught.exception.status_code, 405)
        self.assertEqual(caught.exception.get_codes(), "method_not_allowed")

    def test_default_create_is_rejected(self):
        self.assert_rejected("create", "POST")

    def test_default_update_is_rejected(self):
        self.assert_rejected("update", "PUT")

    def test_default_partial_update_is_rejected(self):
        self.assert_rejected("partial_update", "PATCH")

    def test_default_destroy_is_rejected(self):
        self.assert_rejected("destroy", "DELETE")


if __name__ == "__main__":
    unittest.main()
