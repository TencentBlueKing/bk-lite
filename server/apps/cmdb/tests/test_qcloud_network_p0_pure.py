"""腾讯云 TKE / VPN / NAT P0：实例名、空库存、同行关联命中与未命中。"""
import pytest

pytestmark = pytest.mark.unit


def _runner():
    from apps.cmdb.collection.plugins.community.cloud.qcloud import QCloudCollectionPlugin

    return QCloudCollectionPlugin(inst_name="腾讯云生产", inst_id=1, task_id=8801)


def _row(**labels):
    return labels


def test_p0_field_mappings_cover_models_and_skip_presharekey():
    from apps.cmdb.collection.plugins.community.cloud.qcloud import QCloudCollectionPlugin

    expected = {
        "qcloud_tke_cluster",
        "qcloud_tke_node",
        "qcloud_vpn_gateway",
        "qcloud_customer_gateway",
        "qcloud_vpn_connection",
        "qcloud_nat_gateway",
    }
    assert expected <= set(QCloudCollectionPlugin.field_mappings)
    for model_id in expected:
        assert f"{model_id}_info_gauge" in QCloudCollectionPlugin.metric_names
        mapping = QCloudCollectionPlugin.field_mappings[model_id]
        assert "inst_name" in mapping
        assert "presharekey" not in {key.lower() for key in mapping}
        assert "PreShareKey" not in mapping


def test_empty_vpn_nat_inventory_formats_zero_without_marking_snapshot_incomplete():
    runner = _runner()
    runner.snapshot_complete = True
    runner.collection_metrics_dict = {
        "qcloud_vpn_gateway_info_gauge": [],
        "qcloud_customer_gateway_info_gauge": [],
        "qcloud_vpn_connection_info_gauge": [],
        "qcloud_nat_gateway_info_gauge": [],
    }
    runner.format_metrics()
    assert runner.result["qcloud_vpn_gateway"] == []
    assert runner.result["qcloud_customer_gateway"] == []
    assert runner.result["qcloud_vpn_connection"] == []
    assert runner.result["qcloud_nat_gateway"] == []
    assert runner.snapshot_complete is True


def test_peer_edges_hit_and_miss_without_fabricating():
    runner = _runner()
    runner.collection_metrics_dict = {
        "qcloud_nat_gateway_info_gauge": [
            _row(
                resource_name="nat-a",
                resource_id="nat-1",
                region="ap-guangzhou",
                eip_ids="eip-1,eip-missing,eip-2",
                bandwidth_mbps="100",
                max_concurrent="1000000",
            )
        ],
        "qcloud_vpn_connection_info_gauge": [
            _row(
                resource_name="link-hit",
                resource_id="vpnx-1",
                region="ap-guangzhou",
                vpn_gateway_id="vpngw-1",
                customer_gateway_id="cgw-missing",
            ),
            _row(
                resource_name="link-miss",
                resource_id="vpnx-2",
                region="ap-guangzhou",
                vpn_gateway_id="vpngw-missing",
                customer_gateway_id="",
            ),
        ],
        "qcloud_tke_node_info_gauge": [
            _row(resource_name="ins-1", resource_id="ins-1", region="ap-guangzhou", cluster_id="cls-1", cluster_name="tke-a"),
            _row(resource_name="ins-miss", resource_id="ins-miss", region="ap-guangzhou", cluster_id="cls-missing"),
        ],
        "qcloud_eip_info_gauge": [
            _row(resource_name="eip-a", resource_id="eip-1", region="ap-guangzhou"),
            _row(resource_name="eip-b", resource_id="eip-2", region="ap-guangzhou"),
        ],
        "qcloud_cvm_info_gauge": [
            _row(resource_name="cvm-a", resource_id="ins-1", region="ap-guangzhou", vcpus="2", memory_mb="2048"),
        ],
        "qcloud_tke_cluster_info_gauge": [
            _row(resource_name="tke-a", resource_id="cls-1", region="ap-guangzhou", node_num="3", master_node_num="2"),
        ],
        "qcloud_vpn_gateway_info_gauge": [
            _row(resource_name="gw", resource_id="vpngw-1", region="ap-guangzhou", bandwidth_mbps="20", max_connection="5"),
        ],
        "qcloud_customer_gateway_info_gauge": [],
    }
    runner.format_metrics()

    cluster = runner.result["qcloud_tke_cluster"][0]
    assert cluster["inst_name"] == "tke-a_cls-1"
    assert cluster["node_num"] == 3
    assert cluster["master_node_num"] == 2
    assert cluster["assos"] == [
        {"model_id": "qcloud", "inst_name": "腾讯云生产", "asst_id": "belong", "model_asst_id": "qcloud_tke_cluster_belong_qcloud"}
    ]

    hit_node, miss_node = runner.result["qcloud_tke_node"]
    assert hit_node["inst_name"] == "tke-a_ins-1"
    assert miss_node["inst_name"] == "ins-miss_ins-miss"
    assert hit_node["assos"] == [
        {"model_id": "qcloud", "inst_name": "腾讯云生产", "asst_id": "belong", "model_asst_id": "qcloud_tke_node_belong_qcloud"},
        {
            "model_id": "qcloud_tke_cluster",
            "inst_name": "tke-a_cls-1",
            "asst_id": "belong",
            "model_asst_id": "qcloud_tke_node_belong_qcloud_tke_cluster",
        },
        {"model_id": "qcloud_cvm", "inst_name": "cvm-a_ins-1", "asst_id": "connect", "model_asst_id": "qcloud_tke_node_connect_qcloud_cvm"},
    ]
    assert miss_node["assos"] == [{"model_id": "qcloud", "inst_name": "腾讯云生产", "asst_id": "belong", "model_asst_id": "qcloud_tke_node_belong_qcloud"}]

    hit_link, miss_link = runner.result["qcloud_vpn_connection"]
    assert {item["model_asst_id"] for item in hit_link["assos"]} == {
        "qcloud_vpn_connection_belong_qcloud",
        "qcloud_vpn_connection_connect_qcloud_vpn_gateway",
    }
    assert hit_link["assos"][1]["inst_name"] == "gw_vpngw-1"
    assert miss_link["assos"] == [
        {"model_id": "qcloud", "inst_name": "腾讯云生产", "asst_id": "belong", "model_asst_id": "qcloud_vpn_connection_belong_qcloud"}
    ]

    nat = runner.result["qcloud_nat_gateway"][0]
    assert nat["inst_name"] == "nat-a_nat-1"
    assert nat["bandwidth_mbps"] == 100
    assert nat["max_concurrent"] == 1000000
    assert [item["inst_name"] for item in nat["assos"] if item["asst_id"] == "connect"] == ["eip-a_eip-1", "eip-b_eip-2"]
    assert nat["assos"][0]["model_asst_id"] == "qcloud_nat_gateway_belong_qcloud"


def test_incomplete_identity_is_still_skipped():
    runner = _runner()
    runner.snapshot_complete = True
    runner.collection_metrics_dict = {
        "qcloud_customer_gateway_info_gauge": [
            _row(resource_name="", resource_id="cgw-1"),
            _row(resource_name="peer", resource_id=""),
        ]
    }
    runner.format_metrics()
    assert runner.result["qcloud_customer_gateway"] == []
    assert runner.snapshot_complete is False
