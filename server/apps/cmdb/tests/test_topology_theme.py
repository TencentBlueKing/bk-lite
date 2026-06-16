import pytest
from unittest.mock import patch
from apps.cmdb.services.topology_theme import is_network_device_model, get_topo_themes


@pytest.mark.unit
class TestTopologyTheme:
    @patch("apps.cmdb.services.topology_theme.ModelManage.model_association_search")
    def test_is_network_device_when_belong_assoc_exists(self, mock_search):
        mock_search.return_value = [
            {"src_model_id": "interface", "dst_model_id": "switch", "asst_id": "belong",
             "model_asst_id": "interface_belong_switch"},
        ]
        assert is_network_device_model("switch") is True

    @patch("apps.cmdb.services.topology_theme.ModelManage.model_association_search")
    def test_not_network_device_when_no_belong_assoc(self, mock_search):
        mock_search.return_value = [
            {"src_model_id": "host", "dst_model_id": "switch", "asst_id": "connect",
             "model_asst_id": "host_connect_switch"},
        ]
        assert is_network_device_model("switch") is False

    @patch("apps.cmdb.services.topology_theme.ModelManage.model_association_search")
    def test_get_topo_themes_returns_network(self, mock_search):
        mock_search.return_value = [
            {"src_model_id": "interface", "dst_model_id": "router", "asst_id": "belong",
             "model_asst_id": "interface_belong_router"},
        ]
        assert get_topo_themes("router") == ["network"]

    @patch("apps.cmdb.services.topology_theme.ModelManage.model_association_search")
    def test_get_topo_themes_empty_for_non_network(self, mock_search):
        mock_search.return_value = []
        assert get_topo_themes("host") == []
