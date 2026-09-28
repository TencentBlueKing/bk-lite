from types import SimpleNamespace

import pytest

from apps.core.utils.user_display import build_user_display_map, format_user_identifiers
from apps.core.utils.user_lookup import find_user, is_int_identifier, resolve_actor_user_id
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db


def _user(username, *, domain="domain.com", display_name=""):
    return User.objects.create(
        username=username,
        display_name=display_name,
        email=f"{username}@example.com",
        password="x",
        domain=domain,
    )


def test_is_int_identifier_rejects_bool_and_text():
    assert is_int_identifier(7)
    assert is_int_identifier("7")
    assert not is_int_identifier(True)
    assert not is_int_identifier("alice")
    assert not is_int_identifier("")


def test_find_user_by_id_then_username_and_ignores_blank_values():
    alice = _user("alice")

    assert find_user(alice.id) == alice
    assert find_user(str(alice.id)) == alice
    assert find_user("alice") == alice
    assert find_user("nobody") is None
    assert find_user(None) is None
    assert find_user("") is None
    assert find_user(True) is None


def test_resolve_actor_user_id_prefers_same_domain_then_falls_back_to_username():
    _user("dup", domain="other.com")
    same_domain = _user("dup", domain="domain.com")

    assert resolve_actor_user_id(SimpleNamespace(username="dup", domain="domain.com")) == same_domain.id
    fallback = User.objects.filter(username="dup").first()
    assert resolve_actor_user_id(SimpleNamespace(username="dup", domain="missing.com")) == fallback.id
    assert resolve_actor_user_id(SimpleNamespace(username="ghost", domain="domain.com")) == "ghost"


def test_user_display_map_covers_ids_and_usernames_and_keeps_unknown_values():
    alice = _user("alice", display_name="Alice")
    bob = _user("bob")

    display_map = build_user_display_map([alice.id, "bob", "ghost", None, True])

    assert display_map[str(alice.id)] == "Alice(alice)"
    assert display_map["alice"] == "Alice(alice)"
    assert display_map[str(bob.id)] == "bob"
    assert "ghost" not in display_map
    assert format_user_identifiers([alice.id, "bob", "ghost"], display_map) == ["Alice(alice)", "bob", "ghost"]
    assert format_user_identifiers([]) == []
