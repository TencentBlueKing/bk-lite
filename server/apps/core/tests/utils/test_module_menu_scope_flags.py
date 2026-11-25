"""Pure menu identity flags: no request, user, database or application setup."""
import unittest

from apps.core.utils.module_scope import menu_scope_flags


class ModuleMenuScopeFlagsTests(unittest.TestCase):
    def flags(self, roles, app="cmdb", *, admin=False, auditor=False):
        return menu_scope_flags(roles, app, platform_admin=admin, platform_auditor=auditor)

    def test_module_auditor_overrides_ordinary_app_admin(self):
        self.assertEqual(self.flags(["cmdb--module_auditor", "cmdb--admin"]), (False, True))

    def test_platform_auditor_overrides_module_and_app_admin(self):
        self.assertEqual(self.flags(["cmdb--module_admin", "cmdb--admin"], auditor=True), (False, True))

    def test_platform_admin_keeps_precedence(self):
        self.assertEqual(self.flags(["cmdb--module_auditor"], admin=True), (True, False))

    def test_module_admin_keeps_existing_same_app_precedence(self):
        self.assertEqual(self.flags(["cmdb--module_admin", "cmdb--module_auditor"]), (True, False))

    def test_other_application_module_role_does_not_change_flags(self):
        self.assertEqual(self.flags(["monitor--module_auditor", "cmdb--admin"]), (True, False))
        self.assertEqual(self.flags(["monitor--module_admin"]), (False, False))

    def test_ordinary_roles_unchanged(self):
        self.assertEqual(self.flags(["cmdb--admin"]), (True, False))
        self.assertEqual(self.flags(["cmdb--normal"]), (False, False))
        self.assertEqual(self.flags([]), (False, False))

    def test_no_module_role_keeps_legacy_platform_flags(self):
        self.assertEqual(self.flags(["cmdb--admin"], auditor=True), (True, False))
        self.assertEqual(self.flags(["cmdb--normal"], auditor=True), (False, True))

    def test_excluded_apps_do_not_gain_module_flags(self):
        for app in ["system-manager", "ops-console", ""]:
            with self.subTest(app=app):
                self.assertEqual(self.flags([f"{app}--module_admin", f"{app}--module_auditor"], app), (False, False))


if __name__ == "__main__":
    unittest.main()
