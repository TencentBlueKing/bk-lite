"""node_mgmt 视图层真实行为测试：list/create/destroy/download。

通过 DRF api_client 真实路由调用。仅 mock S3/PackageService 文件边界与权限校验。
断言真实 HTTP 状态码与 DB 副作用。
"""
import pytest
from unittest.mock import MagicMock, patch

from apps.node_mgmt.models import Collector, Controller, PackageVersion
from apps.node_mgmt.models.cloud_region import CloudRegion, SidecarEnv

BASE = "/api/v1/node_mgmt"


# --------------------------------------------------------------------------- #
# Controller list
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_controller_list_returns_display_fields(api_client):
    Controller.objects.create(
        os="linux", cpu_architecture="x86_64", name="Controller", description="desc"
    )
    resp = api_client.get(f"{BASE}/api/controller/")
    assert resp.status_code == 200
    # list 视图为每条记录补充翻译 display 字段
    body = resp.content.decode()
    assert "display_name" in body
    assert "architecture_display" in body


# --------------------------------------------------------------------------- #
# Collector list / create
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_collector_list(api_client):
    Collector.objects.create(
        id="col-view", name="Telegraf", service_type="svc",
        node_operating_system="linux", cpu_architecture="x86_64",
        executable_path="/bin", execute_parameters="-c",
    )
    resp = api_client.get(f"{BASE}/api/collector/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_collector_create(api_client):
    payload = {
        "id": "col-created",
        "name": "NewCollector",
        "service_type": "svc",
        "node_operating_system": "linux",
        "cpu_architecture": "x86_64",
        "executable_path": "/bin/x",
        "execute_parameters": "-c",
    }
    resp = api_client.post(f"{BASE}/api/collector/", payload, format="json")
    assert resp.status_code == 201
    assert Collector.objects.filter(id="col-created").exists()


# --------------------------------------------------------------------------- #
# CloudRegion list / retrieve
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_cloud_region_list(api_client):
    CloudRegion.objects.create(name="cr-view", introduction="intro")
    resp = api_client.get(f"{BASE}/api/cloud_region/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_cloud_region_retrieve(api_client):
    region = CloudRegion.objects.create(name="cr-view-retrieve")
    resp = api_client.get(f"{BASE}/api/cloud_region/{region.id}/")
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# SidecarEnv list / bulk_delete
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_sidecar_env_list(api_client):
    region = CloudRegion.objects.create(name="cr-env-view")
    SidecarEnv.objects.create(cloud_region=region, key="K", value="V", type="str")
    resp = api_client.get(f"{BASE}/api/sidecar_env/")
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# Package list / create / destroy / download
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_package_list(api_client):
    PackageVersion.objects.create(
        type="collector", os="linux", cpu_architecture="x86_64",
        object="telegraf", version="1.0.0", name="telegraf.tar.gz",
    )
    resp = api_client.get(f"{BASE}/api/package/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_package_create_without_file_returns_error(api_client):
    resp = api_client.post(f"{BASE}/api/package/", {"type": "collector"}, format="multipart")
    assert resp.status_code == 400
    assert resp.json()["result"] is False


@pytest.mark.django_db
def test_package_create_missing_params_returns_error(api_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    file = SimpleUploadedFile("telegraf-1.0.0.tar.gz", b"content")
    resp = api_client.post(
        f"{BASE}/api/package/",
        {"file": file, "type": "collector"},
        format="multipart",
    )
    assert resp.status_code == 400
    assert resp.json()["result"] is False


@pytest.mark.django_db
def test_package_create_success_uploads(api_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    file = SimpleUploadedFile("fusion-collectors-1.0.0.tar.gz", b"content")
    with patch("apps.node_mgmt.views.package.PackageService.upload_file") as upload:
        resp = api_client.post(
            f"{BASE}/api/package/",
            {
                "file": file,
                "type": "controller",
                "os": "linux",
                "object": "fusion-collectors",
                "cpu_architecture": "x86_64",
            },
            format="multipart",
        )
    assert resp.status_code == 200
    upload.assert_called_once()
    assert PackageVersion.objects.filter(object="fusion-collectors", version="1.0.0").exists()


@pytest.mark.django_db
def test_package_destroy_deletes_file_and_record(api_client):
    pkg = PackageVersion.objects.create(
        type="collector", os="linux", cpu_architecture="x86_64",
        object="telegraf", version="2.0.0", name="telegraf.tar.gz",
    )
    with patch("apps.node_mgmt.views.package.PackageService.delete_file") as delete:
        resp = api_client.delete(f"{BASE}/api/package/{pkg.id}/")
    delete.assert_called_once()
    assert resp.status_code in (200, 204)
    assert not PackageVersion.objects.filter(id=pkg.id).exists()


@pytest.mark.django_db
def test_package_download(api_client):
    pkg = PackageVersion.objects.create(
        type="collector", os="linux", cpu_architecture="x86_64",
        object="telegraf", version="3.0.0", name="telegraf.tar.gz",
    )
    with patch(
        "apps.node_mgmt.views.package.PackageService.download_file",
        return_value=(b"filecontent", "telegraf.tar.gz"),
    ):
        resp = api_client.get(f"{BASE}/api/package/download/{pkg.id}/")
    assert resp.status_code == 200
