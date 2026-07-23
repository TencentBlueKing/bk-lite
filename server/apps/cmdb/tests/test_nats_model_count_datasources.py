from unittest.mock import patch

import pytest

from apps.cmdb.nats import nats


USER_INFO = {"team": 1, "user": "alice", "language": "zh-CN"}
MODEL_PERMISSIONS = {1: {"inst_names": []}}
INSTANCE_PERMISSIONS = {1: {"inst_names": []}}


@pytest.mark.unit
class TestModelClassificationOptions:
    @patch.object(nats.ModelManage, "search_model")
    @patch.object(nats.ClassificationManage, "search_model_classification")
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_returns_visible_authorized_categories_in_cmdb_order(
        self, permission_mock, classifications_mock, models_mock
    ):
        classifications_mock.return_value = [
            {"classification_id": "host", "classification_name": "主机"},
            {"classification_id": "middleware", "classification_name": "中间件"},
            {"classification_id": "database", "classification_name": "数据库"},
        ]
        models_mock.return_value = [
            {"model_id": "nginx", "classification_id": "middleware"},
            {"model_id": "linux", "classification_id": "host"},
        ]

        result = nats.get_model_classification_options(user_info=USER_INFO)

        assert result == {
            "items": [
                {"classification_id": "host", "classification_name": "主机"},
                {"classification_id": "middleware", "classification_name": "中间件"},
            ]
        }
        permission_mock.assert_called_once_with(USER_INFO)
        classifications_mock.assert_called_once_with(language="zh")
        models_mock.assert_called_once_with(language="zh", permissions_map=MODEL_PERMISSIONS)

    @patch.object(nats, "_build_nats_model_permission_map", return_value=None)
    def test_returns_empty_items_without_model_permission(self, permission_mock):
        assert nats.get_model_classification_options(user_info=USER_INFO) == {"items": []}
        permission_mock.assert_called_once_with(USER_INFO)


@pytest.mark.unit
class TestClassificationModelInstanceCounts:
    @patch.object(nats.InstanceManage, "model_inst_count")
    @patch.object(nats.ModelManage, "search_model")
    @patch.object(nats.ClassificationManage, "search_model_classification")
    @patch.object(nats, "_build_nats_permission_map", return_value=INSTANCE_PERMISSIONS)
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_filters_zero_and_sorts_count_desc_then_name(
        self,
        model_permission_mock,
        instance_permission_mock,
        classifications_mock,
        models_mock,
        count_mock,
    ):
        classifications_mock.return_value = [
            {"classification_id": "middleware", "classification_name": "中间件"}
        ]
        models_mock.return_value = [
            {"model_id": "apache", "model_name": "Apache", "classification_id": "middleware"},
            {"model_id": "tomcat", "model_name": "Tomcat", "classification_id": "middleware"},
            {"model_id": "nginx", "model_name": "Nginx", "classification_id": "middleware"},
            {"model_id": "zero", "model_name": "Zero", "classification_id": "middleware"},
        ]
        count_mock.return_value = {"apache": 100, "tomcat": 10, "nginx": 10, "zero": 0}

        result = nats.get_classification_model_instance_counts(
            classification_id="middleware", user_info=USER_INFO
        )

        assert result == {
            "items": [
                {"label": "Apache", "value": 100},
                {"label": "Nginx", "value": 10},
                {"label": "Tomcat", "value": 10},
            ]
        }
        model_permission_mock.assert_called_once_with(USER_INFO)
        instance_permission_mock.assert_called_once_with(USER_INFO)
        classifications_mock.assert_called_once_with(language="zh")
        models_mock.assert_called_once_with(
            language="zh",
            permissions_map=MODEL_PERMISSIONS,
            classification_ids=["middleware"],
        )
        count_mock.assert_called_once_with(permissions_map=INSTANCE_PERMISSIONS)

    @pytest.mark.parametrize("classification_id", [None, "", "   "])
    def test_returns_empty_items_for_blank_classification(self, classification_id):
        assert nats.get_classification_model_instance_counts(
            classification_id=classification_id, user_info=USER_INFO
        ) == {"items": []}

    @patch.object(nats.ModelManage, "search_model")
    @patch.object(
        nats.ClassificationManage,
        "search_model_classification",
        return_value=[{"classification_id": "host", "classification_name": "主机"}],
    )
    def test_returns_empty_items_for_unknown_or_hidden_classification(
        self, classifications_mock, models_mock
    ):
        assert nats.get_classification_model_instance_counts(
            classification_id="middleware", user_info=USER_INFO
        ) == {"items": []}
        classifications_mock.assert_called_once_with(language="zh")
        models_mock.assert_not_called()

    @patch.object(
        nats.ClassificationManage,
        "search_model_classification",
        return_value=[{"classification_id": "middleware", "classification_name": "中间件"}],
    )
    @patch.object(nats, "_build_nats_permission_map", return_value=INSTANCE_PERMISSIONS)
    @patch.object(nats, "_build_nats_model_permission_map", return_value=None)
    def test_returns_empty_items_without_model_permission(
        self, model_permission_mock, instance_permission_mock, classifications_mock
    ):
        assert nats.get_classification_model_instance_counts(
            classification_id="middleware", user_info=USER_INFO
        ) == {"items": []}
        model_permission_mock.assert_called_once_with(USER_INFO)
        instance_permission_mock.assert_called_once_with(USER_INFO)

    @patch.object(
        nats.ClassificationManage,
        "search_model_classification",
        return_value=[{"classification_id": "middleware", "classification_name": "中间件"}],
    )
    @patch.object(nats, "_build_nats_permission_map", return_value=None)
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_returns_empty_items_without_instance_permission(
        self, model_permission_mock, instance_permission_mock, classifications_mock
    ):
        assert nats.get_classification_model_instance_counts(
            classification_id="middleware", user_info=USER_INFO
        ) == {"items": []}
        model_permission_mock.assert_called_once_with(USER_INFO)
        instance_permission_mock.assert_called_once_with(USER_INFO)


@pytest.mark.unit
def test_nats_cmdb_language_normalization():
    assert nats._resolve_nats_cmdb_language({"language": "en-US"}) == "en"
    assert nats._resolve_nats_cmdb_language({"locale": "zh-CN"}) == "zh"
