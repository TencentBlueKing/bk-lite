from types import SimpleNamespace

from apps.core.utils.platform_scope import bypasses_write_guard, has_unrestricted_org_scope


def test_superuser_has_scope_and_write_bypass():
    user = SimpleNamespace(is_superuser=True, is_auditor=False)
    assert has_unrestricted_org_scope(user) is True
    assert bypasses_write_guard(user) is True


def test_auditor_has_scope_but_no_write_bypass():
    user = SimpleNamespace(is_superuser=False, is_auditor=True)
    assert has_unrestricted_org_scope(user) is True
    assert bypasses_write_guard(user) is False


def test_normal_user_has_neither():
    user = SimpleNamespace(is_superuser=False, is_auditor=False)
    assert has_unrestricted_org_scope(user) is False
    assert bypasses_write_guard(user) is False


def test_module_admin_is_unrestricted_only_inside_that_app():
    user = SimpleNamespace(is_superuser=False, is_auditor=False, roles=["cmdb--module_admin"])
    assert has_unrestricted_org_scope(user) is False
    assert has_unrestricted_org_scope(user, "cmdb") is True
    assert bypasses_write_guard(user, "cmdb") is True
    assert has_unrestricted_org_scope(user, "monitor") is False
    assert bypasses_write_guard(user, "monitor") is False


def test_platform_auditor_stays_readonly_with_a_module_admin_role():
    from apps.core.utils.platform_scope import is_readonly_scope

    user = SimpleNamespace(is_superuser=False, is_auditor=True, roles=["cmdb--module_admin"])
    assert has_unrestricted_org_scope(user, "cmdb") is True
    assert bypasses_write_guard(user, "cmdb") is False
    assert is_readonly_scope(user, "cmdb") is True


def test_module_auditor_can_switch_orgs_but_cannot_write():
    from apps.core.utils.platform_scope import is_readonly_scope

    user = SimpleNamespace(is_superuser=False, is_auditor=False, roles=["cmdb--module_auditor"])
    assert has_unrestricted_org_scope(user, "cmdb") is True
    assert bypasses_write_guard(user, "cmdb") is False
    assert is_readonly_scope(user, "cmdb") is True
    assert is_readonly_scope(user, "monitor") is False
