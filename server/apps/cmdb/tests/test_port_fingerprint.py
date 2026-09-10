import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.models.collect_model import PortFingerprint
from apps.cmdb.services.port_fingerprint import ports_for_scan_type, scan_database_ports_by_type, sync_builtin_port_fingerprints
from apps.cmdb.views.port_fingerprint import PortFingerprintViewSet

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(authenticated_user):
    user = authenticated_user
    user.is_superuser = True
    user.group_list = [{"id": 1}]
    user.roles = ["admin"]
    user.domain = "domain.com"
    return user


def _req(method, user, data=None, query=None, pk=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    path = "/x/"
    if query:
        path = "/x/?" + "&".join(f"{key}={value}" for key, value in query.items())
    request = fn(path) if data is None else fn(path, data=data, format="json")
    force_authenticate(request, user=user)
    if pk is None:
        return request
    return request, pk


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def test_sync_creates_three_builtin_database_ports():
    result = sync_builtin_port_fingerprints()
    assert result["created"] == 3
    rows = list(PortFingerprint.objects.order_by("port").values_list("port", "target_type", "built_in"))
    assert rows == [(1433, "mssql", True), (3306, "mysql", True), (5432, "postgresql", True)]


def test_sync_does_not_overwrite_user_row_on_same_port_type():
    PortFingerprint.objects.create(port=3306, target_type="mysql", protocol="tcp", built_in=False)
    result = sync_builtin_port_fingerprints()
    assert result["created"] == 2
    assert result["skipped_user"] == 1
    row = PortFingerprint.objects.get(port=3306, target_type="mysql")
    assert row.built_in is False


def test_same_port_can_have_middleware_and_database_types():
    sync_builtin_port_fingerprints()
    PortFingerprint.objects.create(port=3306, target_type="redis", protocol="tcp", built_in=False)
    assert PortFingerprint.objects.filter(port=3306).count() == 2
    assert ports_for_scan_type("mysql") == [3306]
    assert ports_for_scan_type("redis") == []


def test_ports_for_scan_type_includes_user_added_database_ports():
    sync_builtin_port_fingerprints()
    PortFingerprint.objects.create(port=3307, target_type="mysql", protocol="tcp", built_in=False)
    assert ports_for_scan_type("mysql") == [3306, 3307]
    by_type = scan_database_ports_by_type()
    assert by_type["mysql"] == [3306, 3307]
    assert by_type["postgresql"] == [5432]
    assert by_type["mssql"] == [1433]


def test_init_command_writes_builtins():
    output = StringIO()
    call_command("init_port_fingerprint", stdout=output, stderr=output)
    assert PortFingerprint.objects.filter(built_in=True).count() == 3
    assert "新增=3" in output.getvalue()


def test_batch_init_calls_init_port_fingerprint():
    text = Path("apps/core/management/commands/batch_init.py").read_text(encoding="utf-8")
    assert 'call_command("init_port_fingerprint")' in text


def test_create_duplicate_port_type_rejected(superuser):
    PortFingerprint.objects.create(port=3306, target_type="mysql", protocol="tcp", built_in=True)
    request = _req("post", superuser, data={"port": 3306, "target_type": "mysql"})
    response = PortFingerprintViewSet.as_view({"post": "create"})(request)
    body = _body(response)
    assert body["result"] is False
    assert "已存在" in body["message"]


def test_create_middleware_type_allowed(superuser):
    request = _req("post", superuser, data={"port": 6379, "target_type": "redis"})
    response = PortFingerprintViewSet.as_view({"post": "create"})(request)
    assert response.status_code == 201
    row = PortFingerprint.objects.get(port=6379, target_type="redis")
    assert row.built_in is False
    assert row.protocol == "tcp"


def test_delete_builtin_rejected(superuser):
    row = PortFingerprint.objects.create(port=3306, target_type="mysql", protocol="tcp", built_in=True)
    request = _req("delete", superuser)
    response = PortFingerprintViewSet.as_view({"delete": "destroy"})(request, pk=row.id)
    body = _body(response)
    assert body["result"] is False
    assert "内置" in body["message"]
    assert PortFingerprint.objects.filter(pk=row.id).exists()


def test_delete_user_row_allowed(superuser):
    row = PortFingerprint.objects.create(port=3307, target_type="mysql", protocol="tcp", built_in=False)
    request = _req("delete", superuser)
    response = PortFingerprintViewSet.as_view({"delete": "destroy"})(request, pk=row.id)
    assert response.status_code in (200, 204)
    assert not PortFingerprint.objects.filter(pk=row.id).exists()
