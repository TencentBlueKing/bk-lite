from unittest.mock import patch

import pytest

from apps.cmdb.nats import nats


USER_INFO = {"team": 1, "user": "alice", "language": "zh-CN"}
MODEL_PERMISSIONS = {1: {"inst_names": []}}
INSTANCE_PERMISSIONS = {1: {"inst_names": []}}


@pytest.mark.unit
class TestRegionOptions:
    @patch.object(nats, "extract_region_options", return_value=[{"label": "本部", "value": "本部"}])
    @patch.object(nats.ClassificationManage, "search_model_classification", return_value=[{"classification_id": "c1"}])
    @patch.object(nats.ModelManage, "search_model", return_value=[{"classification_id": "c1"}])
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_returns_service_options(self, permission, models, classifications, service):
        assert nats.get_region_options(user_info=USER_INFO) == {"items": [{"label": "本部", "value": "本部"}]}
        models.assert_called_once_with(language="zh", permissions_map=MODEL_PERMISSIONS)
        service.assert_called_once_with([{"classification_id": "c1"}], {"c1"})

    @patch.object(nats, "_build_nats_model_permission_map", return_value=None)
    def test_no_permission_returns_empty(self, _permission):
        assert nats.get_region_options(user_info=USER_INFO) == {"items": []}


@pytest.mark.unit
class TestRegionResourceOverview:
    @patch.object(nats, "build_region_resource_items", return_value=[{"label": "主机", "value": 3}])
    @patch.object(nats.InstanceManage, "group_inst_count", return_value={"m1": 3})
    @patch.object(nats, "extract_region_options", return_value=[{"label": "本部", "value": "本部"}])
    @patch.object(nats.ClassificationManage, "search_model_classification", return_value=[{"classification_id": "c1"}])
    @patch.object(nats.ModelManage, "search_model", return_value=[{"model_id": "m1", "classification_id": "c1"}])
    @patch.object(nats, "_build_nats_permission_map", return_value=INSTANCE_PERMISSIONS)
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_exact_region_filter_and_items(self, model_perm, inst_perm, models, classifications, regions, group, build):
        result = nats.get_region_resource_overview(region="本部", user_info=USER_INFO)
        assert result == {"items": [{"label": "主机", "value": 3}]}
        group.assert_called_once_with(
            group_by_attr="model_id", permissions_map=INSTANCE_PERMISSIONS,
            params=[{"field": "tag", "type": "list[]", "value": ["region:本部"]}],
        )
        build.assert_called_once()

    @pytest.mark.parametrize("region", [None, "", "未知"])
    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_blank_or_unknown_region_returns_empty(self, _permission, region):
        with patch.object(nats, "extract_region_options", return_value=[{"label": "本部", "value": "本部"}]), patch.object(nats, "_build_nats_permission_map", return_value=INSTANCE_PERMISSIONS):
            assert nats.get_region_resource_overview(region=region, user_info=USER_INFO) == {"items": []}

    @patch.object(nats, "_build_nats_model_permission_map", return_value=MODEL_PERMISSIONS)
    def test_propagates_group_count_error(self, _permission):
        with patch.object(nats, "_build_nats_permission_map", return_value=INSTANCE_PERMISSIONS), patch.object(nats.ModelManage, "search_model", return_value=[]), patch.object(nats.ClassificationManage, "search_model_classification", return_value=[]), patch.object(nats, "extract_region_options", return_value=[{"label": "本部", "value": "本部"}]), patch.object(nats.InstanceManage, "group_inst_count", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                nats.get_region_resource_overview(region="本部", user_info=USER_INFO)
