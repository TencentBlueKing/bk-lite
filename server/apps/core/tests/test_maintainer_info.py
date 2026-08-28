from apps.core.models.maintainer_info import maintainer_kwargs


def test_maintainer_kwargs_prefers_actor_context():
    fields = maintainer_kwargs({"username": "alice", "domain": "corp.com"})
    assert fields == {
        "created_by": "alice",
        "updated_by": "alice",
        "domain": "corp.com",
        "updated_by_domain": "corp.com",
    }


def test_maintainer_kwargs_falls_back_to_system():
    fields = maintainer_kwargs(None, include_created=False)
    assert fields == {
        "updated_by": "system",
        "updated_by_domain": "domain.com",
    }


def test_maintainer_kwargs_explicit_operator_overrides_actor():
    fields = maintainer_kwargs({"username": "alice"}, operator="bob", domain="other.com")
    assert fields["created_by"] == "bob"
    assert fields["domain"] == "other.com"
