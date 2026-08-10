from plugins.inputs.qcloud.region_scope import resolve_collection_regions


def test_selected_region_limits_qcloud_collection_scope():
    assert resolve_collection_regions(
        "ap-guangzhou",
        [
            {"Region": "ap-guangzhou", "RegionState": "AVAILABLE"},
            {"Region": "ap-shanghai", "RegionState": "AVAILABLE"},
        ],
    ) == ["ap-guangzhou"]


def test_missing_selected_region_keeps_legacy_all_region_scope():
    assert resolve_collection_regions(
        "",
        [
            {"Region": "ap-guangzhou", "RegionState": "AVAILABLE"},
            {"Region": "ap-shanghai", "RegionState": "UNAVAILABLE"},
        ],
    ) == [
        "ap-guangzhou",
    ]
