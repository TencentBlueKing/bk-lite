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
