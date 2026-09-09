"""云采集凭据链路契约：HTTP 入口 → CollectionRequest → SDK Manager。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import api.collect as collect_api
import httpx
import pytest
from core.collection.contracts import CollectOutcomeStatus, TargetCollectionContext
from core.collection.plugins import ConfigurationCollectionPlugin
from core.collection.runtime import Submission, SubmissionStatus
from plugins.inputs.aliyun.aliyun_info import CwAliyun
from plugins.inputs.hwcloud.huaweicloud_info import HuaweiCloudManager
from plugins.inputs.qcloud.qcloud_info import TencentCloudManager
from sanic import Sanic


class AdmissionApplication:
    def __init__(self):
        self.requests = []

    async def submit(self, request):
        self.requests.append(request)
        return Submission(
            task_id=request.task_id,
            status=SubmissionStatus.ACCEPTED,
            fence=1,
        )


def _telegraf_request(headers):
    async def receive_body():
        return None

    return SimpleNamespace(
        method="GET",
        path="/api/collect/collect_info",
        query_string="",
        query_args=[],
        headers=headers,
        receive_body=receive_body,
    )


@asynccontextmanager
async def _http_client():
    app = Sanic("cloud-credential-delivery")
    app.config.AUTO_EXTEND = False
    app.config.TOUCHUP = False
    app.blueprint(collect_api.collect_router)
    app.asgi = True
    await app._startup()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://stargazer.test",
    ) as client:
        yield client


async def _deliver_to_manager(monkeypatch, headers, manager_factory):
    admission = AdmissionApplication()
    managers = []
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: admission)

    response = await collect_api.collect(_telegraf_request(headers))
    assert response.status == 202
    request = admission.requests[0]

    class ManagerBoundaryService:
        def __init__(self, params):
            managers.append(manager_factory(params))

        async def collect(self):
            return 'cloud_credential_delivery{collect_status="success"} 1'

    context = TargetCollectionContext(
        task_id=request.task_id,
        plugin_ref=request.plugin_ref,
        fence=1,
        params=request.params,
    )
    outcome = await ConfigurationCollectionPlugin(
        service_factory=ManagerBoundaryService,
    ).collect(request.targets[0], request.credentials[0], context)

    assert outcome.status is CollectOutcomeStatus.SUCCESS
    assert "secret_id" not in request.params
    assert "secret_key" not in request.params
    return managers[0], request


@pytest.mark.asyncio
async def test_qcloud_http_credentials_reach_sdk_manager(monkeypatch):
    manager, request = await _deliver_to_manager(
        monkeypatch,
        {
            "cmdbplugin_name": "qcloud_info",
            "cmdbmodel_id": "qcloud",
            "cmdbexecutor_type": "protocol",
            "cmdbsecret_id": "SENTINEL_QCLOUD_SECRET_ID",
            "cmdbsecret_key": "SENTINEL_QCLOUD_SECRET_KEY",
            "cmdbregion_id": "ap-guangzhou",
            "cmdbcollect_task_id": "3",
            "instance_id": "cmdb_3",
            "instance_type": "cmdb_qcloud",
            "collect_type": "http",
            "config_type": "qcloud",
        },
        TencentCloudManager,
    )

    assert request.plugin_ref == "qcloud.config"
    assert manager.secret_id == "SENTINEL_QCLOUD_SECRET_ID"
    assert manager.secret_key == "SENTINEL_QCLOUD_SECRET_KEY"
    assert manager.region_id == "ap-guangzhou"
    sdk_credential = manager.get_credentials()
    assert sdk_credential.secret_id == "SENTINEL_QCLOUD_SECRET_ID"
    assert sdk_credential.secret_key == "SENTINEL_QCLOUD_SECRET_KEY"


@pytest.mark.asyncio
async def test_aliyun_http_credentials_reach_sdk_manager(monkeypatch):
    manager, request = await _deliver_to_manager(
        monkeypatch,
        {
            "cmdbplugin_name": "aliyun_info",
            "cmdbmodel_id": "aliyun",
            "cmdbexecutor_type": "protocol",
            "cmdbsecret_id": "SENTINEL_ALIYUN_ACCESS_KEY_ID",
            "cmdbsecret_key": "SENTINEL_ALIYUN_ACCESS_KEY_SECRET",
            "cmdbregion_id": "cn-guangzhou",
            "cmdbcollect_task_id": "2",
            "instance_id": "cmdb_2",
            "instance_type": "cmdb_aliyun",
            "collect_type": "http",
            "config_type": "aliyun",
        },
        CwAliyun,
    )

    assert request.plugin_ref == "aliyun.config"
    assert manager.AccessKey == "SENTINEL_ALIYUN_ACCESS_KEY_ID"
    assert manager.AccessSecret == "SENTINEL_ALIYUN_ACCESS_KEY_SECRET"
    assert manager.RegionId == "cn-guangzhou"


@pytest.mark.asyncio
async def test_hwcloud_http_credentials_reach_sdk_manager(monkeypatch):
    manager, request = await _deliver_to_manager(
        monkeypatch,
        {
            "cmdbplugin_name": "huaweicloud_info",
            "cmdbmodel_id": "hwcloud",
            "cmdbexecutor_type": "protocol",
            "cmdbaccessKey": "SENTINEL_HWCLOUD_ACCESS_KEY",
            "cmdbaccessSecret": "SENTINEL_HWCLOUD_ACCESS_SECRET",
            "cmdbproject_id": "sentinel-project-id",
            "cmdbregion": "cn-south-1",
            "cmdbcollect_task_id": "4",
            "instance_id": "cmdb_4",
            "instance_type": "cmdb_hwcloud",
            "collect_type": "http",
            "config_type": "hwcloud",
        },
        HuaweiCloudManager,
    )

    assert request.plugin_ref == "hwcloud.config"
    assert "accessKey" not in request.params
    assert "accessSecret" not in request.params
    assert manager.account == "SENTINEL_HWCLOUD_ACCESS_KEY"
    assert manager.password == "SENTINEL_HWCLOUD_ACCESS_SECRET"
    assert manager.project_id == "sentinel-project-id"
    assert manager.region == "cn-south-1"


@pytest.mark.asyncio
async def test_hwcloud_real_http_transport_preserves_credential_field_names(monkeypatch):
    admission = AdmissionApplication()
    monkeypatch.setattr(collect_api, "get_collection_application", lambda: admission)

    async with _http_client() as client:
        response = await client.get(
            "/collect/collect_info",
            headers={
                "cmdbplugin_name": "huaweicloud_info",
                "cmdbmodel_id": "hwcloud",
                "cmdbexecutor_type": "protocol",
                "cmdbaccessKey": "SENTINEL_HWCLOUD_ACCESS_KEY",
                "cmdbaccessSecret": "SENTINEL_HWCLOUD_ACCESS_SECRET",
                "cmdbproject_id": "sentinel-project-id",
                "cmdbregion": "cn-south-1",
                "cmdbcollect_task_id": "4",
                "instance_id": "cmdb_4",
                "instance_type": "cmdb_hwcloud",
                "collect_type": "http",
                "config_type": "hwcloud",
            },
        )

    assert response.status_code == 202
    request = admission.requests[0]
    assert request.credentials[0]["accessKey"] == "SENTINEL_HWCLOUD_ACCESS_KEY"
    assert request.credentials[0]["accessSecret"] == "SENTINEL_HWCLOUD_ACCESS_SECRET"
    assert "accessKey" not in request.params
    assert "accessSecret" not in request.params
    assert "SENTINEL_HWCLOUD_ACCESS_KEY" not in request.digest
    assert "SENTINEL_HWCLOUD_ACCESS_SECRET" not in request.digest
