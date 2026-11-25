"""Pure role-ID set policy; no identities, requests, ORM or authentication."""
import unittest

from apps.core.utils.module_scope import ModuleRoleGrantError, ModuleRoleIdentityTransitionError, validate_module_role_change


class ModuleRoleChangePolicyTests(unittest.TestCase):
    def test_identity_change_revoke_has_specific_error(self):
        with self.assertRaises(ModuleRoleIdentityTransitionError):
            validate_module_role_change([1], [10, 2], {10, 11}, can_assign=False, identity_transition=True)

    def test_platform_grant_authority_can_clear_module_roles(self):
        self.assertIsNone(validate_module_role_change([1], [10], {10, 11}, can_assign=True, identity_transition=True))

    def test_no_module_roles_keeps_existing_identity_change_path(self):
        self.assertIsNone(validate_module_role_change([1], [2], {10, 11}, can_assign=False, identity_transition=True))

    def test_profile_edit_preserves_hidden_module_roles(self):
        self.assertIsNone(validate_module_role_change([10, 3], [10, 2], {10, 11}, can_assign=False))

    def test_real_module_grant_and_revoke_stay_denied(self):
        for submitted, existing in [([10], []), ([], [10]), ([11], [10])]:
            with self.subTest(submitted=submitted, existing=existing):
                with self.assertRaises(ModuleRoleGrantError) as caught:
                    validate_module_role_change(submitted, existing, {10, 11}, can_assign=False)
                self.assertNotIsInstance(caught.exception, ModuleRoleIdentityTransitionError)

    def test_identity_flag_does_not_allow_new_module_role(self):
        with self.assertRaises(ModuleRoleGrantError) as caught:
            validate_module_role_change([10], [], {10}, can_assign=False, identity_transition=True)
        self.assertNotIsInstance(caught.exception, ModuleRoleIdentityTransitionError)

    def test_downgrade_does_not_restore_cleared_module_roles(self):
        self.assertIsNone(validate_module_role_change([2], [1], {10, 11}, can_assign=False))


if __name__ == "__main__":
    unittest.main()
