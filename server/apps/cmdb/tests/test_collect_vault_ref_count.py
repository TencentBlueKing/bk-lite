from types import SimpleNamespace

from apps.cmdb.nats import nats as cmdb_nats


def test_cmdb_ref_count_queries_only_vault_candidates(monkeypatch):
    observed = []

    class Query:
        def count(self):
            return 2

    class Manager:
        def filter(self, **kwargs):
            observed.append(kwargs)
            return Query()

    monkeypatch.setattr(cmdb_nats, "CollectModels", SimpleNamespace(objects=Manager()))
    result = cmdb_nats.cmdb_count_credential_refs(["crd-1", "crd-1", "crd-2"])
    assert result == {"result": True, "data": {"counts": {"crd-1": 2, "crd-2": 2}}}
    assert observed == [
        {"credential__contains": [{"credential_source": "vault", "vault_credential_id": "crd-1"}]},
        {"credential__contains": [{"credential_source": "vault", "vault_credential_id": "crd-2"}]},
    ]


def test_cmdb_ref_count_rejects_unbounded_request():
    assert cmdb_nats.cmdb_count_credential_refs(["crd"] * 101)["result"] is False
