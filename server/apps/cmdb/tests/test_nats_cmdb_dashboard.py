import pytest

from apps.cmdb.nats import nats as N


@pytest.mark.parametrize(
    ("locale", "classification_name", "model_name"),
    [
        ("zh-Hans", "硬件设备", "物理服务器"),
        ("en", "Hardware Device", "Physical Server"),
    ],
)
def test_cmdb_model_instance_top_uses_request_locale(
    monkeypatch,
    locale,
    classification_name,
    model_name,
):
    monkeypatch.setattr(N, "_build_nats_model_permission_map", lambda _user_info: {})
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {})
    monkeypatch.setattr(
        N.ClassificationManage,
        "search_model_classification",
        lambda language: [
            {
                "classification_id": "harware",
                "classification_name": classification_name if language == locale else "wrong language",
            }
        ],
    )
    monkeypatch.setattr(
        N.ModelManage,
        "search_model",
        lambda language, permissions_map: [
            {
                "model_id": "physical_server",
                "model_name": model_name if language == locale else "wrong language",
                "classification_id": "harware",
            }
        ],
    )
    monkeypatch.setattr(N.InstanceManage, "model_inst_count", lambda permissions_map: {"physical_server": 63})

    result = N.get_cmdb_model_instance_top(
        limit=5,
        user_info={"locale": locale},
    )

    assert result == {
        "result": True,
        "data": [
            {
                "model": model_name,
                "model_id": "physical_server",
                "classification": classification_name,
                "classification_id": "harware",
                "count": 63,
            }
        ],
        "message": "",
    }


@pytest.mark.parametrize(
    ("locale", "classification_name", "model_name"),
    [
        ("zh-Hans", "硬件设备", "物理服务器"),
        ("en", "Hardware Device", "Physical Server"),
    ],
)
def test_model_inst_statistics_uses_request_locale(
    monkeypatch,
    locale,
    classification_name,
    model_name,
):
    monkeypatch.setattr(N, "_build_nats_model_permission_map", lambda _user_info: {})
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {})
    monkeypatch.setattr(
        N.ClassificationManage,
        "search_model_classification",
        lambda language: [
            {
                "classification_id": "harware",
                "classification_name": classification_name if language == locale else "wrong language",
            }
        ],
    )
    monkeypatch.setattr(
        N.ModelManage,
        "search_model",
        lambda language, permissions_map: [
            {
                "model_id": "physical_server",
                "model_name": model_name if language == locale else "wrong language",
                "classification_id": "harware",
            }
        ],
    )
    monkeypatch.setattr(N.InstanceManage, "model_inst_count", lambda permissions_map: {"physical_server": 63})

    result = N.get_model_inst_statistics(user_info={"locale": locale})

    assert result == {
        "result": True,
        "data": [
            {
                "classification": classification_name,
                "model": model_name,
                "model_id": "physical_server",
                "count": 63,
            }
        ],
        "message": "",
    }
