"""Tests for model/classification visibility and layout features."""

import pytest
from unittest.mock import MagicMock

from apps.cmdb.services.classification import ClassificationManage
from apps.cmdb.services.model import ModelManage


@pytest.fixture
def fake_graph(monkeypatch):
    """Mock GraphClient used inside services."""
    fake = MagicMock()
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    monkeypatch.setattr(
        "apps.cmdb.services.model.GraphClient", lambda: fake
    )
    monkeypatch.setattr(
        "apps.cmdb.services.classification.GraphClient", lambda: fake
    )
    return fake


class TestSearchModelVisibility:
    def _models(self):
        return [
            {"model_id": "host", "model_name": "Host",
             "classification_id": "infra", "group": ["default"],
             "order_id": 1, "is_visible": True},
            {"model_id": "switch", "model_name": "Switch",
             "classification_id": "infra", "group": ["default"],
             "order_id": 0, "is_visible": False},
            {"model_id": "legacy", "model_name": "Legacy",
             "classification_id": "infra", "group": ["default"]},
        ]

    def test_default_filters_hidden_and_backfills(self, fake_graph):
        fake_graph.query_entity.return_value = (self._models(), 3)
        result = ModelManage.search_model(language="en")
        ids = [m["model_id"] for m in result]
        assert "switch" not in ids
        assert set(ids) == {"host", "legacy"}
        legacy = next(m for m in result if m["model_id"] == "legacy")
        assert legacy["order_id"] == 0
        assert all(m["is_visible"] is True for m in result)

    def test_include_hidden_returns_all_with_flag(self, fake_graph):
        fake_graph.query_entity.return_value = (self._models(), 3)
        result = ModelManage.search_model(language="en", include_hidden=True)
        ids = [m["model_id"] for m in result]
        assert set(ids) == {"host", "switch", "legacy"}
        legacy = next(m for m in result if m["model_id"] == "legacy")
        assert legacy["is_visible"] is True

    def test_default_sort_passes_order_id_to_query(self, fake_graph):
        fake_graph.query_entity.return_value = ([], 0)
        ModelManage.search_model(language="en")
        kwargs = fake_graph.query_entity.call_args.kwargs
        assert kwargs.get("order") == "order_id"
        assert kwargs.get("order_type") == "ASC"


class TestUpdateModelOrders:
    def test_writes_order_and_visibility(self, fake_graph):
        fake_graph.query_entity.return_value = (
            [{"_id": 101, "model_id": "host"}], 1,
        )
        ModelManage.update_model_orders([
            {"model_id": "host", "order_id": 3, "is_visible": False},
        ])
        args, _ = fake_graph.set_entity_properties.call_args
        label, ids, props, *_ = args
        assert ids == [101]
        assert props == {"order_id": 3, "is_visible": False}

    def test_omits_visibility_if_not_provided(self, fake_graph):
        fake_graph.query_entity.return_value = (
            [{"_id": 101, "model_id": "host"}], 1,
        )
        ModelManage.update_model_orders([
            {"model_id": "host", "order_id": 3},
        ])
        args, _ = fake_graph.set_entity_properties.call_args
        _, _, props, *_ = args
        assert props == {"order_id": 3}


class TestSearchClassificationVisibility:
    def _classifications(self):
        return [
            {"classification_id": "infra", "classification_name": "Infra",
             "order": 2, "is_visible": True},
            {"classification_id": "biz", "classification_name": "Biz",
             "order": 0, "is_visible": False},
            {"classification_id": "legacy", "classification_name": "Legacy"},
        ]

    def test_default_filters_hidden_and_sorts(self, fake_graph):
        fake_graph.query_entity.side_effect = [
            (self._classifications(), 3),
            ([], 0),
        ]
        result = ClassificationManage.search_model_classification(language="en")
        ids = [c["classification_id"] for c in result]
        assert ids == ["infra", "legacy"]
        assert all(c["is_visible"] is True for c in result)

    def test_include_hidden_returns_all_sorted(self, fake_graph):
        fake_graph.query_entity.side_effect = [
            (self._classifications(), 3),
            ([], 0),
        ]
        result = ClassificationManage.search_model_classification(
            language="en", include_hidden=True,
        )
        ids = [c["classification_id"] for c in result]
        assert ids == ["biz", "infra", "legacy"]
        legacy = next(c for c in result if c["classification_id"] == "legacy")
        assert legacy["order"] == 999
        assert legacy["is_visible"] is True


class TestUpdateClassificationLayout:
    def test_writes_order_and_visibility_per_item(self, fake_graph):
        fake_graph.query_entity.return_value = (
            [
                {"_id": 1, "classification_id": "infra"},
                {"_id": 2, "classification_id": "biz"},
            ], 2,
        )
        ClassificationManage.update_classification_layout([
            {"classification_id": "infra", "order": 0, "is_visible": True},
            {"classification_id": "biz", "order": 1, "is_visible": False},
        ])
        calls = fake_graph.set_entity_properties.call_args_list
        assert len(calls) == 2
        args1, _ = calls[0]
        assert args1[1] == [1]
        assert args1[2] == {"order": 0, "is_visible": True}
        args2, _ = calls[1]
        assert args2[1] == [2]
        assert args2[2] == {"order": 1, "is_visible": False}

    def test_skips_unknown_classification(self, fake_graph):
        fake_graph.query_entity.return_value = (
            [{"_id": 1, "classification_id": "infra"}], 1,
        )
        ClassificationManage.update_classification_layout([
            {"classification_id": "ghost", "order": 0, "is_visible": True},
        ])
        fake_graph.set_entity_properties.assert_not_called()


from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


MODEL_BASE_URL = "/api/v1/cmdb/api/model/"


@pytest.fixture
def superuser(db):
    User = get_user_model()
    return User.objects.create_superuser(
        username="root", email="root@example.com", password="x",
    )


@pytest.fixture
def normal_user(db):
    User = get_user_model()
    user = User.objects.create_user(
        username="alice", email="a@example.com", password="x",
    )
    # Grant cmdb View so HasPermission decorator does not 403 early —
    # tests target the view-level behavior, not the permission gate.
    user.permission = {"cmdb": {"model_management-View"}}
    return user


@pytest.fixture
def patch_view_helpers(monkeypatch):
    """Bypass DB-backed helpers used by the list view."""
    monkeypatch.setattr(
        "apps.cmdb.views.model.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda *a, **kw: {},
    )
    monkeypatch.setattr(
        "apps.cmdb.views.model.get_default_group_id",
        lambda: ("default", None),
    )
    monkeypatch.setattr(
        "apps.cmdb.views.model.get_current_team_from_request",
        lambda request: "default",
    )


@pytest.mark.django_db
class TestModelLayoutAPI:
    def test_list_default_passes_include_hidden_false(
        self, superuser, monkeypatch, patch_view_helpers,
    ):
        calls = {"include_hidden": None}
        def fake_search(**kwargs):
            calls.update(kwargs)
            return []
        monkeypatch.setattr(
            "apps.cmdb.views.model.ModelManage.search_model", fake_search,
        )
        client = APIClient()
        client.force_authenticate(user=superuser)
        client.get(MODEL_BASE_URL)
        assert calls.get("include_hidden") is False

    def test_list_include_hidden_true_for_superuser(
        self, superuser, monkeypatch, patch_view_helpers,
    ):
        calls = {}
        def fake_search(**kwargs):
            calls.update(kwargs)
            return []
        monkeypatch.setattr(
            "apps.cmdb.views.model.ModelManage.search_model", fake_search,
        )
        client = APIClient()
        client.force_authenticate(user=superuser)
        client.get(MODEL_BASE_URL + "?include_hidden=true")
        assert calls.get("include_hidden") is True

    def test_list_ignores_include_hidden_for_normal_user(
        self, normal_user, monkeypatch, patch_view_helpers,
    ):
        calls = {"include_hidden": None}
        def fake_search(**kwargs):
            calls.update(kwargs)
            return []
        monkeypatch.setattr(
            "apps.cmdb.views.model.ModelManage.search_model", fake_search,
        )
        client = APIClient()
        client.force_authenticate(user=normal_user)
        client.get(MODEL_BASE_URL + "?include_hidden=true")
        assert calls.get("include_hidden") is False

    def test_save_layout_writes_both(self, superuser, monkeypatch):
        cls_calls, mdl_calls = [], []
        monkeypatch.setattr(
            "apps.cmdb.views.model.ClassificationManage.update_classification_layout",
            lambda items: cls_calls.append(items),
        )
        monkeypatch.setattr(
            "apps.cmdb.views.model.ModelManage.update_model_orders",
            lambda orders: mdl_calls.append(orders),
        )
        client = APIClient()
        client.force_authenticate(user=superuser)
        resp = client.post(
            MODEL_BASE_URL + "save_layout/",
            {
                "classifications": [
                    {"classification_id": "infra", "order": 0, "is_visible": True},
                ],
                "models": [
                    {"model_id": "host", "order_id": 0, "is_visible": True},
                ],
            },
            format="json",
        )
        assert resp.status_code == 200
        assert cls_calls and mdl_calls

    def test_save_layout_forbidden_for_normal_user(self, normal_user):
        client = APIClient()
        client.force_authenticate(user=normal_user)
        resp = client.post(
            MODEL_BASE_URL + "save_layout/",
            {"classifications": [], "models": []},
            format="json",
        )
        assert resp.status_code in (401, 403)


class TestClassificationListAPI:
    def test_default_include_hidden_false(self, superuser, monkeypatch):
        calls = {"include_hidden": None}
        def fake_search(language, include_hidden=False):
            calls["include_hidden"] = include_hidden
            return []
        monkeypatch.setattr(
            "apps.cmdb.views.classification.ClassificationManage.search_model_classification",
            fake_search,
        )
        client = APIClient()
        client.force_authenticate(user=superuser)
        client.get("/api/v1/cmdb/api/classification/")
        assert calls["include_hidden"] is False

    def test_include_hidden_true_for_superuser(self, superuser, monkeypatch):
        calls = {"include_hidden": None}
        def fake_search(language, include_hidden=False):
            calls["include_hidden"] = include_hidden
            return []
        monkeypatch.setattr(
            "apps.cmdb.views.classification.ClassificationManage.search_model_classification",
            fake_search,
        )
        client = APIClient()
        client.force_authenticate(user=superuser)
        client.get("/api/v1/cmdb/api/classification/?include_hidden=true")
        assert calls["include_hidden"] is True

    def test_include_hidden_ignored_for_normal_user(self, normal_user, monkeypatch):
        calls = {"include_hidden": None}
        def fake_search(language, include_hidden=False):
            calls["include_hidden"] = include_hidden
            return []
        monkeypatch.setattr(
            "apps.cmdb.views.classification.ClassificationManage.search_model_classification",
            fake_search,
        )
        client = APIClient()
        client.force_authenticate(user=normal_user)
        client.get("/api/v1/cmdb/api/classification/?include_hidden=true")
        assert calls["include_hidden"] is False


class TestSingleModelLookup:
    def test_search_model_info_returns_hidden_model(self, fake_graph):
        """search_model_info must NOT apply the is_visible filter — hidden
        models must remain resolvable by ID so instance pages can still
        render the model name for references to a hidden model."""
        fake_graph.query_entity.return_value = (
            [{
                "model_id": "ghost",
                "model_name": "Ghost",
                "classification_id": "infra",
                "is_visible": False,
                "order_id": 0,
            }], 1,
        )
        result = ModelManage.search_model_info("ghost")
        assert result["model_id"] == "ghost"
        assert result["is_visible"] is False


@pytest.mark.django_db
class TestSaveLayoutAtomicity:
    def test_reverts_classifications_when_model_update_fails(
        self, superuser, monkeypatch,
    ):
        apply_calls = []
        snapshot_calls = []

        def fake_snapshot(ids):
            snapshot_calls.append(list(ids))
            return [{"classification_id": "infra", "order": 7, "is_visible": True}]

        def fake_apply(items):
            apply_calls.append(items)

        def boom(orders):
            raise RuntimeError("graph offline")

        monkeypatch.setattr(
            "apps.cmdb.views.model.ClassificationManage.snapshot_classification_layout",
            fake_snapshot,
        )
        monkeypatch.setattr(
            "apps.cmdb.views.model.ClassificationManage.update_classification_layout",
            fake_apply,
        )
        monkeypatch.setattr(
            "apps.cmdb.views.model.ModelManage.update_model_orders",
            boom,
        )

        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=superuser)
        resp = client.post(
            "/api/v1/cmdb/api/model/save_layout/",
            {
                "classifications": [
                    {"classification_id": "infra", "order": 0, "is_visible": True},
                ],
                "models": [
                    {"model_id": "host", "order_id": 0, "is_visible": True},
                ],
            },
            format="json",
        )
        # the view should bubble the failure
        assert resp.status_code >= 500
        # snapshot taken before write
        assert snapshot_calls == [["infra"]]
        # apply called twice: once forward, once for revert with the snapshot
        assert len(apply_calls) == 2
        assert apply_calls[1] == [{"classification_id": "infra", "order": 7, "is_visible": True}]
