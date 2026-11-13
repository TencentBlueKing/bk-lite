import uuid

import pytest

from apps.system_mgmt.models import IMAccountAssociation, IMNotificationSyncRun, IMNotificationUserMapping, IntegrationInstance, User


def _instance(name, provider_key):
    return IntegrationInstance.objects.create(
        name=name,
        provider_key=provider_key,
        enabled=True,
        status="ready",
        capability_status={"im_notification": "ready"},
        config={},
    )


def _association(name, instance):
    return IMAccountAssociation.objects.create(
        name=name,
        integration_instance=instance,
        platform_match_field="email",
        external_match_field="email",
        external_receive_field="user_id",
        status="ready",
    )


@pytest.mark.django_db
def test_list_records_searches_by_name_and_filters_instance(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    feishu = _instance("feishu-records", "feishu")
    wecom = _instance("wecom-records", "wecom")
    alpha = _association("alpha-assoc", feishu)
    beta = _association("beta-assoc", wecom)
    IMNotificationSyncRun.objects.create(account_association=alpha, status="success", summary="alpha done", trigger_mode="manual")
    IMNotificationSyncRun.objects.create(account_association=beta, status="partial", summary="beta done", trigger_mode="schedule")

    searched = api_client.get(
        "/api/v1/system_mgmt/im_account_association/records/",
        {"page": 1, "page_size": 10, "search": "alpha"},
    )

    assert searched.status_code == 200
    assert searched.data["count"] == 1
    assert searched.data["items"][0]["account_association_name"] == "alpha-assoc"
    assert searched.data["items"][0]["status"] == "success"
    assert searched.data["items"][0]["trigger_mode"] == "manual"

    scoped = api_client.get(
        "/api/v1/system_mgmt/im_account_association/records/",
        {"page": 1, "page_size": 10, "integration_instance": wecom.id},
    )

    assert scoped.status_code == 200
    assert scoped.data["count"] == 1
    assert scoped.data["items"][0]["account_association_name"] == "beta-assoc"
    assert scoped.data["items"][0]["status"] == "partial"


@pytest.mark.django_db
def test_list_records_omits_payload_and_rejects_non_numeric_instance(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])

    instance = _instance("payload-instance", "feishu")
    association = _association("payload-assoc", instance)
    IMNotificationSyncRun.objects.create(
        account_association=association,
        status="failed",
        summary="visible summary",
        trigger_mode="manual",
        payload={"token": "secret-sentinel-PAYLOAD"},
        locked_config_snapshot={"app_secret": "secret-sentinel-SNAPSHOT"},
    )

    listed = api_client.get(
        "/api/v1/system_mgmt/im_account_association/records/",
        {"page": 1, "page_size": 10},
    )

    assert listed.status_code == 200
    item = listed.data["items"][0]
    assert item["account_association_name"] == "payload-assoc"
    assert item["summary"] == "visible summary"
    assert "payload" not in item
    assert "locked_config_snapshot" not in item
    assert "secret-sentinel-PAYLOAD" not in listed.content.decode()
    assert "secret-sentinel-SNAPSHOT" not in listed.content.decode()

    rejected = api_client.get(
        "/api/v1/system_mgmt/im_account_association/",
        {"integration_instance": "not-a-number"},
    )
    assert rejected.status_code == 400
    assert "must be an integer" in rejected.content.decode()


@pytest.mark.django_db
def test_account_association_options_are_capped_and_reject_non_numeric_instance(api_client, authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    monkeypatch.setattr(
        "apps.system_mgmt.viewset.im_notification_channel_viewset.ACCOUNT_ASSOCIATION_OPTION_LIMIT",
        2,
    )

    instance = _instance("options-instance", "feishu")
    for name in ("alpha", "beta", "gamma"):
        _association(name, instance)

    listed = api_client.get("/api/v1/system_mgmt/im_notification_channel/account_association_options/")

    assert listed.status_code == 200
    names = [item["name"] for item in listed.json()["data"]]
    assert names == ["alpha", "beta"]

    rejected = api_client.get(
        "/api/v1/system_mgmt/im_notification_channel/account_association_options/",
        {"integration_instance_id": "not-a-number"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["result"] is False
    assert rejected.json()["message"] == "Integration instance must be an integer"


@pytest.mark.django_db
def test_mappings_omit_snapshot_and_match_context(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])

    instance = _instance("mapping-instance", "feishu")
    association = _association("mapping-assoc", instance)
    user = User.objects.create(
        user_id=str(uuid.uuid4()),
        username="mapper",
        display_name="Mapper",
        email="mapper@example.com",
        password="",
        domain="domain.com",
    )
    IMNotificationUserMapping.objects.create(
        account_association=association,
        user=user,
        external_identity_key="user_id",
        external_identity_value="ou_mapper",
        external_receive_key="user_id",
        external_display_name="Mapper",
        match_context={"raw": "secret-sentinel-CONTEXT"},
        external_snapshot={"user_id": "ou_mapper", "token": "secret-sentinel-SNAPSHOT"},
    )

    listed = api_client.get(
        f"/api/v1/system_mgmt/im_account_association/{association.id}/mappings/",
        {"page": 1, "page_size": 10},
    )

    assert listed.status_code == 200
    item = listed.data["items"][0]
    assert item["username"] == "mapper"
    assert item["display_name"] == "Mapper"
    assert item["external_identity_value"] == "ou_mapper"
    assert "external_snapshot" not in item
    assert "match_context" not in item
    body = listed.content.decode()
    assert "secret-sentinel-SNAPSHOT" not in body
    assert "secret-sentinel-CONTEXT" not in body
