import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.filters.collect_filters import ProcessFingerprintFilter
from apps.cmdb.models.collect_model import ProcessFingerprint
from apps.cmdb.services.process_fingerprint import (
    BUILTIN_PROCESS_FINGERPRINTS,
    enabled_process_fingerprints,
    linux_process_matches,
    sync_builtin_process_fingerprints,
)
from apps.cmdb.views.process_fingerprint import ProcessFingerprintViewSet

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(authenticated_user):
    user = authenticated_user
    user.is_superuser = True
    user.group_list = [{"id": 1}]
    user.roles = ["admin"]
    user.domain = "domain.com"
    return user


def _req(method, user, data=None, pk=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn("/x/") if data is None else fn("/x/", data=data, format="json")
    force_authenticate(request, user=user)
    if pk is None:
        return request
    return request, pk


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def test_sync_creates_mysql_process_that_matches_mysqld():
    result = sync_builtin_process_fingerprints()
    assert result["created"] == len(BUILTIN_PROCESS_FINGERPRINTS)
    row = ProcessFingerprint.objects.get(target_type="mysql", built_in=True)
    assert linux_process_matches(row.linux_process, "/usr/sbin/mysqld --datadir=/var/lib/mysql")
    assert linux_process_matches(row.linux_process, "mariadbd")


def test_sync_does_not_overwrite_user_row_on_same_key():
    ProcessFingerprint.objects.create(target_type="mysql", linux_process=r"mysqld|mariadbd", windows_image="mysqld.exe", built_in=False)
    result = sync_builtin_process_fingerprints()
    assert result["skipped_user"] == 1
    row = ProcessFingerprint.objects.get(target_type="mysql", linux_process=r"mysqld|mariadbd")
    assert row.built_in is False


def test_enabled_process_fingerprints_omits_disabled_rows():
    sync_builtin_process_fingerprints()
    ProcessFingerprint.objects.filter(target_type="mysql").update(enabled=False)
    enabled_types = {item["target_type"] for item in enabled_process_fingerprints()}
    assert "mysql" not in enabled_types
    assert "nginx" in enabled_types


def test_init_command_writes_builtins():
    output = StringIO()
    call_command("init_process_fingerprint", stdout=output, stderr=output)
    assert ProcessFingerprint.objects.filter(built_in=True).count() == len(BUILTIN_PROCESS_FINGERPRINTS)
    assert f"新增={len(BUILTIN_PROCESS_FINGERPRINTS)}" in output.getvalue()


def test_batch_init_calls_init_process_fingerprint():
    text = Path("apps/core/management/commands/batch_init.py").read_text(encoding="utf-8")
    assert 'call_command("init_process_fingerprint")' in text


def test_create_rejects_cloud_account(superuser):
    request = _req("post", superuser, data={"target_type": "aliyun_account", "linux_process": "foo"})
    response = ProcessFingerprintViewSet.as_view({"post": "create"})(request)
    body = _body(response)
    assert body["result"] is False
    assert "不支持" in body["message"]


def test_create_mysql_process_allowed(superuser):
    request = _req("post", superuser, data={"target_type": "mysql", "linux_process": "mysqld-custom"})
    response = ProcessFingerprintViewSet.as_view({"post": "create"})(request)
    assert response.status_code == 201
    row = ProcessFingerprint.objects.get(linux_process="mysqld-custom")
    assert row.built_in is False
    assert row.target_type == "mysql"


def test_search_filter_matches_linux_or_windows():
    sync_builtin_process_fingerprints()
    qs = ProcessFingerprintFilter({"search": "w3wp"}, queryset=ProcessFingerprint.objects.all()).qs
    assert qs.count() == 1
    assert qs.first().target_type == "iis"
    linux_qs = ProcessFingerprintFilter({"search": "mysqld"}, queryset=ProcessFingerprint.objects.all()).qs
    assert linux_qs.filter(target_type="mysql").exists()


def test_delete_builtin_rejected(superuser):
    sync_builtin_process_fingerprints()
    row = ProcessFingerprint.objects.get(target_type="mysql", built_in=True)
    request = _req("delete", superuser)
    response = ProcessFingerprintViewSet.as_view({"delete": "destroy"})(request, pk=row.id)
    body = _body(response)
    assert body["result"] is False
    assert "内置" in body["message"]
    assert ProcessFingerprint.objects.filter(pk=row.id).exists()
