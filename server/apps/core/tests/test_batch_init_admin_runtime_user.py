"""部署引导写入的 admin 必须能作为 OpenAPI 系统令牌的 acting user。"""

from types import SimpleNamespace

import pytest
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError

from apps.base.models.user import User as BaseUser
from apps.core.management.commands.batch_init import Command
from apps.system_mgmt.models import Group
from apps.system_mgmt.models import User as SystemUser

pytestmark = pytest.mark.django_db


def _create_system_admin(*, domain="domain.com", email="admin@bklite.net"):
    group, _ = Group.objects.get_or_create(name="Default", parent_id=0)
    return SystemUser.objects.create(
        username="admin",
        domain=domain,
        display_name="admin",
        email=email,
        password=make_password("password"),
        group_list=[group.id],
    )


def test_ensure_admin_runtime_user_creates_auth_user_for_default_domain_admin():
    _create_system_admin()
    assert not BaseUser._default_manager.filter(username="admin", domain="domain.com").exists()

    Command._create_admin_runtime_user()

    user = BaseUser._default_manager.get(username="admin", domain="domain.com")
    assert user.is_active is True
    assert user.is_superuser is True
    assert user.is_staff is True
    assert user.email == "admin@bklite.net"


def test_ensure_admin_runtime_user_is_idempotent_and_does_not_overwrite_existing():
    _create_system_admin()
    existing = BaseUser._default_manager.create(
        username="admin",
        domain="domain.com",
        email="kept@example.com",
        is_superuser=False,
        is_staff=False,
        is_active=True,
    )

    Command._create_admin_runtime_user()
    Command._create_admin_runtime_user()

    user = BaseUser._default_manager.get(pk=existing.pk)
    assert BaseUser._default_manager.filter(username="admin", domain="domain.com").count() == 1
    assert user.email == "kept@example.com"
    assert user.is_superuser is False


def test_ensure_admin_runtime_user_skips_when_default_domain_admin_missing():
    _create_system_admin(domain="other.example")

    Command._create_admin_runtime_user()

    assert not BaseUser._default_manager.filter(username="admin").exists()


def test_create_admin_runtime_user_treats_integrity_race_as_success(monkeypatch):
    _create_system_admin()

    def raced_get_or_create(*args, **kwargs):
        BaseUser._default_manager.create(username="admin", domain="domain.com", email="race@example.com")
        raise IntegrityError("duplicate key")

    monkeypatch.setattr(BaseUser._default_manager, "get_or_create", raced_get_or_create)

    Command._create_admin_runtime_user()

    assert BaseUser._default_manager.filter(username="admin", domain="domain.com").exists()


def test_runtime_user_failure_does_not_roll_back_system_admin():
    admin = _create_system_admin()
    cmd = Command()
    cmd.stdout = SimpleNamespace(messages=[], write=lambda m: cmd.stdout.messages.append(m))
    cmd.style = SimpleNamespace(WARNING=lambda m: f"WARN:{m}")

    def boom():
        raise RuntimeError("runtime user table missing")

    cmd._create_admin_runtime_user = boom
    cmd._ensure_admin_runtime_user()

    assert SystemUser.objects.filter(pk=admin.pk).exists()
    assert not BaseUser._default_manager.filter(username="admin", domain="domain.com").exists()
    assert any("运行时账号初始化跳过（RuntimeError）" in message for message in cmd.stdout.messages)
