import io
import logging
import sys
import zipfile
from pathlib import Path
import pytest
from rest_framework.test import APIClient

from apps.system_mgmt.apps import HandleConfig
from apps.system_mgmt.models import IntegrationInstance, OperationLog
from apps.system_mgmt.providers import loader
from apps.system_mgmt.providers.registry import provider_registry

UPLOAD_URL = "/api/v1/system_mgmt/provider_pack/"
PROVIDERS_URL = "/api/v1/system_mgmt/integration_instance/providers/"
MAX_PACK_BYTES = 10 * 1024 * 1024


def _enterprise_upload_available():
    try:
        from apps.system_mgmt.models import UploadedProviderPack  # noqa: F401
        from apps.system_mgmt.enterprise.viewset.provider_pack_viewset import (  # noqa: F401
            ProviderPackViewSet,
        )
    except ImportError:
        return False
    return True


requires_enterprise_upload = pytest.mark.skipif(
    not _enterprise_upload_available(),
    reason="社区版未叠加 enterprise provider pack 上传实现",
)


def _drop_uploaded_import_trees():
    for name in list(sys.modules):
        if name.startswith("bk_lite_uploaded_provider_"):
            del sys.modules[name]


@pytest.fixture(autouse=True)
def clean_provider_state(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_PACK_CACHE_DIR", str(tmp_path / "provider-pack-cache"))
    loader.reset_builtin_providers()
    _drop_uploaded_import_trees()
    yield
    loader.reset_builtin_providers()
    _drop_uploaded_import_trees()


def _language_yaml(name: str) -> str:
    return f"name: {name}\ndescription: {name} provider pack for tests.\n"


def _capability_block(key: str, *, include_login_auth: bool) -> str:
    if not include_login_auth:
        return '        "capabilities": [],\n'
    return (
        '        "capabilities": [\n'
        "            {\n"
        '                "key": "login_auth",\n'
        '                "name": "Login",\n'
        f'                "adapter_key": "{key}.login_auth",\n'
        '                "adapter_path": "adapters.client.PackLoginAuthAdapter",\n'
        "            }\n"
        "        ],\n"
    )


def _minimal_pack_files(
    key: str = "acme",
    *,
    init_extra: str = "",
    marker: str = "ok",
    include_login_auth: bool = False,
) -> dict[str, str]:
    return {
        f"{key}/__init__.py": "from .manifest import PROVIDER_MANIFEST\n" + init_extra,
        f"{key}/manifest.py": (
            "from apps.system_mgmt.providers.schemas import ProviderManifest\n\n"
            "PROVIDER_MANIFEST = ProviderManifest.model_validate(\n"
            "    {\n"
            f'        "key": "{key}",\n'
            f'        "name": "{key.title()}",\n'
            f'        "base_connection_adapter_key": "{key}.base_connection",\n'
            '        "base_connection_adapter_path": "adapters.base_connection.PackBaseConnectionAdapter",\n'
            f"{_capability_block(key, include_login_auth=include_login_auth)}"
            "    }\n"
            ")\n"
        ),
        f"{key}/language/en.yaml": _language_yaml(key.title()),
        f"{key}/language/zh-Hans.yaml": _language_yaml(key.title()),
        f"{key}/adapters/__init__.py": "",
        f"{key}/adapters/client.py": (
            "from apps.system_mgmt.providers.runtime import CapabilityExecutionResult\n\n"
            "class PackLoginAuthAdapter:\n"
            "    @classmethod\n"
            "    def test_connection(cls, config, provider_key, capability_key, **kwargs):\n"
            "        return CapabilityExecutionResult.success_result('login')\n"
            if include_login_auth
            else ""
        ),
        f"{key}/adapters/base_connection.py": (
            "from apps.system_mgmt.providers.runtime import CapabilityExecutionResult\n\n"
            "class PackBaseConnectionAdapter:\n"
            "    @classmethod\n"
            "    def test_connection(cls, config, provider_key, capability_key, **kwargs):\n"
            f"        return CapabilityExecutionResult.success_result('{marker}')\n"
        ),
    }


def _zip_bytes(files: dict[str, str], *, extra_bytes: bytes | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        if extra_bytes is not None:
            archive.writestr("padding.bin", extra_bytes)
    return buffer.getvalue()


def _auth_client(user, *, is_superuser: bool, permissions: set[str] | None = None) -> APIClient:
    user.is_superuser = is_superuser
    user.permission = {
        "system-manager": set(permissions)
        if permissions is not None
        else {"integration_center-Add", "integration_center-View"}
    }
    user.save(update_fields=["is_superuser"])
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_system_mgmt_ready_does_not_sync_uploaded_packs(monkeypatch):
    def fail_if_synced():
        raise AssertionError("SystemMgmtConfig.ready() 不应同步上传包")

    monkeypatch.setattr(loader, "_sync_uploaded_provider_packs", fail_if_synced)
    HandleConfig("apps.system_mgmt", __import__("apps.system_mgmt")).ready()


def test_registry_read_syncs_uploaded_packs_after_builtin(monkeypatch):
    calls = []
    original_load = loader.load_builtin_providers

    def tracking_load(force=False):
        calls.append("builtin")
        return original_load(force=force)

    def tracking_sync():
        calls.append("uploaded")

    monkeypatch.setattr(loader, "load_builtin_providers", tracking_load)
    monkeypatch.setattr(loader, "_sync_uploaded_provider_packs", tracking_sync)

    provider_registry.list()

    assert calls == ["builtin", "uploaded"]


def test_community_urls_module_does_not_register_provider_pack_route():
    source = Path(loader.__file__).resolve().parents[1].joinpath("urls.py").read_text(encoding="utf-8")
    assert "provider_pack" not in source
    assert "ProviderPackViewSet" not in source


def test_community_provider_pack_migration_exists_without_upload_route():
    app_root = Path(loader.__file__).resolve().parents[1]
    migration = (app_root / "migrations" / "0048_uploaded_provider_pack.py").read_text(encoding="utf-8")
    assert "0047_group_is_delete" in migration
    assert "CreateModel" in migration
    assert "UploadedProviderPack" in migration
    assert "ProviderPackCatalog" not in migration
    from apps.system_mgmt.models import UploadedProviderPack

    assert UploadedProviderPack._meta.app_label == "system_mgmt"


@requires_enterprise_upload
@pytest.mark.django_db
def test_superuser_upload_new_key_is_listed_and_can_create_instance(
    authenticated_user, tmp_path
):
    from apps.system_mgmt.models import UploadedProviderPack

    client = _auth_client(authenticated_user, is_superuser=True)
    payload = _zip_bytes(_minimal_pack_files("acme"))

    response = client.post(UPLOAD_URL, {"file": io.BytesIO(payload)}, format="multipart")

    assert response.status_code == 201
    assert response.data["key"] == "acme"
    assert "archive" not in response.data
    assert UploadedProviderPack.objects.filter(key="acme").count() == 1
    assert UploadedProviderPack.objects.get(key="acme").pack_revision == 1
    assert {item["key"] for item in client.get(PROVIDERS_URL).data} >= {"acme", "feishu"}

    instance = IntegrationInstance.objects.create(
        name="acme-prod",
        provider_key="acme",
        config={},
        team=[1],
    )
    assert instance.provider_key == "acme"
    assert provider_registry.get("acme") is not None

    pack_list = client.get(UPLOAD_URL)
    assert pack_list.status_code == 200
    listed = {item["key"]: item for item in pack_list.data}
    assert listed["acme"]["source"] == "uploaded"
    assert listed["wecom"]["source"] == "builtin"


@requires_enterprise_upload
@pytest.mark.django_db
def test_nonsuperuser_with_view_can_list_packs(authenticated_user):
    client = _auth_client(
        authenticated_user,
        is_superuser=False,
        permissions={"integration_center-View"},
    )
    response = client.get(UPLOAD_URL)
    assert response.status_code == 200


@requires_enterprise_upload
@pytest.mark.django_db
def test_nonsuperuser_with_add_can_upload(authenticated_user, tmp_path):
    from apps.system_mgmt.models import UploadedProviderPack

    client = _auth_client(authenticated_user, is_superuser=False)
    payload = _zip_bytes(_minimal_pack_files("acme"))

    response = client.post(UPLOAD_URL, {"file": io.BytesIO(payload)}, format="multipart")

    assert response.status_code == 201
    assert UploadedProviderPack.objects.filter(key="acme").count() == 1


@requires_enterprise_upload
@pytest.mark.django_db
def test_view_only_upload_returns_403(authenticated_user, tmp_path):
    from apps.system_mgmt.models import UploadedProviderPack

    client = _auth_client(
        authenticated_user,
        is_superuser=False,
        permissions={"integration_center-View"},
    )
    payload = _zip_bytes(_minimal_pack_files("acme"))

    response = client.post(UPLOAD_URL, {"file": io.BytesIO(payload)}, format="multipart")

    assert response.status_code == 403
    assert not UploadedProviderPack.objects.exists()


@requires_enterprise_upload
@pytest.mark.django_db
def test_replace_without_edit_permission_returns_403(authenticated_user, tmp_path):
    from apps.system_mgmt.models import UploadedProviderPack

    client = _auth_client(authenticated_user, is_superuser=False)
    payload = _zip_bytes(_minimal_pack_files("acme"))
    assert client.post(UPLOAD_URL, {"file": io.BytesIO(payload)}, format="multipart").status_code == 201

    replaced = client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme", marker="v2"))), "replace": "true"},
        format="multipart",
    )

    assert replaced.status_code == 403
    assert UploadedProviderPack.objects.get(key="acme").pack_revision == 1


@requires_enterprise_upload
@pytest.mark.django_db
def test_builtin_key_upload_is_rejected(authenticated_user, tmp_path):
    from apps.system_mgmt.models import UploadedProviderPack

    client = _auth_client(authenticated_user, is_superuser=True)
    payload = _zip_bytes(_minimal_pack_files("wecom"))

    response = client.post(UPLOAD_URL, {"file": io.BytesIO(payload)}, format="multipart")

    assert response.status_code == 400
    assert not UploadedProviderPack.objects.exists()
    assert provider_registry.get("wecom") is not None


@requires_enterprise_upload
@pytest.mark.django_db
def test_existing_uploaded_key_returns_409_without_replace(
    authenticated_user, tmp_path
):
    from apps.system_mgmt.models import UploadedProviderPack

    client = _auth_client(authenticated_user, is_superuser=True)
    first = client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart")
    assert first.status_code == 201

    second = client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme", marker="v2")))},
        format="multipart",
    )

    assert second.status_code == 409
    assert second.data["key"] == "acme"
    assert second.data["pack_revision"] == 1
    assert second.data["instance_count"] == 0
    assert "author_version" in second.data
    assert UploadedProviderPack.objects.filter(key="acme").count() == 1
    assert UploadedProviderPack.objects.get(key="acme").pack_revision == 1


@requires_enterprise_upload
@pytest.mark.django_db
def test_zip_slip_is_rejected(authenticated_user, tmp_path):
    from apps.system_mgmt.models import UploadedProviderPack

    client = _auth_client(authenticated_user, is_superuser=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../evil.py", "print(1)\n")
        archive.writestr("acme/__init__.py", "")

    response = client.post(UPLOAD_URL, {"file": io.BytesIO(buffer.getvalue())}, format="multipart")

    assert response.status_code == 400
    assert not UploadedProviderPack.objects.exists()


@requires_enterprise_upload
@pytest.mark.django_db
def test_oversized_zip_is_rejected(authenticated_user, tmp_path):
    from apps.system_mgmt.models import UploadedProviderPack

    client = _auth_client(authenticated_user, is_superuser=True)
    payload = _zip_bytes(_minimal_pack_files("acme"), extra_bytes=b"x" * (MAX_PACK_BYTES + 1))

    response = client.post(UPLOAD_URL, {"file": io.BytesIO(payload)}, format="multipart")

    assert response.status_code == 400
    assert not UploadedProviderPack.objects.exists()


@requires_enterprise_upload
@pytest.mark.django_db
def test_trial_load_failure_does_not_persist(authenticated_user, tmp_path, caplog):
    from apps.system_mgmt.models import UploadedProviderPack
    from apps.system_mgmt.enterprise.provider_pack_archive import uploaded_pack_import_name

    client = _auth_client(authenticated_user, is_superuser=True)
    files = _minimal_pack_files("broken")
    files["broken/__init__.py"] = "raise RuntimeError('boom')\n"
    files["broken/sentinel.bin"] = "ZIP-SENTINEL-CREDENTIAL-DO-NOT-LOG"
    cache_root = Path(tmp_path / "provider-pack-cache")
    sentinel = b"ZIP-SENTINEL-CREDENTIAL-DO-NOT-LOG"

    with caplog.at_level(logging.ERROR, logger="system-manager"):
        response = client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(files))}, format="multipart")

    assert response.status_code == 400
    assert not UploadedProviderPack.objects.exists()
    assert not (cache_root / "broken").exists() or not any((cache_root / "broken").rglob("*"))
    leftover = [
        name
        for name in __import__("sys").modules
        if name.startswith("bk_lite_uploaded_provider_staging_") or name == uploaded_pack_import_name("broken", 1)
    ]
    assert leftover == []
    records = [
        record
        for record in caplog.records
        if record.name == "system-manager" and "provider_pack_upload_failed" in record.msg
    ]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=provider_pack_upload_failed pack_key=%s failed_stage=%s error_type=%s"
    assert record.args == ("broken", "trial_load", "RuntimeError")
    formatted = logging.Formatter().format(record)
    assert sentinel not in formatted.encode()
    assert "boom" in formatted


@requires_enterprise_upload
@pytest.mark.django_db
def test_adapter_resolve_failure_does_not_persist(authenticated_user, tmp_path):
    from apps.system_mgmt.enterprise.provider_pack_archive import uploaded_pack_import_name
    from apps.system_mgmt.models import UploadedProviderPack
    from apps.system_mgmt.providers.registry import capability_adapter_registry

    client = _auth_client(authenticated_user, is_superuser=True)
    files = _minimal_pack_files("badadapt")
    files["badadapt/manifest.py"] = files["badadapt/manifest.py"].replace(
        "adapters.base_connection.PackBaseConnectionAdapter",
        "adapters.base_connection.MissingAdapter",
    )
    cache_root = Path(tmp_path / "provider-pack-cache")

    response = client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(files))}, format="multipart")

    assert response.status_code == 400
    assert not UploadedProviderPack.objects.exists()
    assert "badadapt" not in provider_registry._providers
    assert "badadapt.base_connection" not in capability_adapter_registry._adapters
    leftover = [
        name
        for name in __import__("sys").modules
        if name.startswith("bk_lite_uploaded_provider_staging_") or name == uploaded_pack_import_name("badadapt", 1)
    ]
    assert leftover == []
    assert not (cache_root / "badadapt").exists() or not any((cache_root / "badadapt").rglob("*"))


@requires_enterprise_upload
@pytest.mark.django_db
def test_persist_failure_does_not_register_new_key(authenticated_user, monkeypatch):
    from apps.system_mgmt.models import UploadedProviderPack

    def boom(*_args, **_kwargs):
        raise ValueError("persist-boom")

    monkeypatch.setattr(UploadedProviderPack.objects, "create", boom)
    client = _auth_client(authenticated_user, is_superuser=True)
    response = client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("persistfail")))},
        format="multipart",
    )

    assert response.status_code == 400
    assert "persistfail" not in provider_registry._providers
    assert not UploadedProviderPack.objects.filter(key="persistfail").exists()


@requires_enterprise_upload
@pytest.mark.django_db
def test_failed_pack_retry_waits_for_sync_ttl(authenticated_user, monkeypatch):
    from apps.system_mgmt.enterprise import provider_pack_archive, provider_pack_sync

    client = _auth_client(authenticated_user, is_superuser=True)
    assert (
        client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart").status_code
        == 201
    )
    _corrupt_uploaded_pack_archive("acme")
    provider_registry.list()
    assert "acme" in provider_pack_sync.get_uploaded_pack_load_failures()

    def fail_extract(*_args, **_kwargs):
        raise AssertionError("failed pack retry must wait for TTL")

    monkeypatch.setattr(provider_pack_archive, "extract_provider_pack_zip", fail_extract)
    monkeypatch.setattr(provider_pack_sync, "extract_provider_pack_zip", fail_extract)
    provider_registry.list()


@requires_enterprise_upload
@pytest.mark.django_db
def test_list_provider_packs_does_not_select_archive(authenticated_user):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client = _auth_client(authenticated_user, is_superuser=True)
    assert client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart").status_code == 201

    with CaptureQueriesContext(connection) as captured:
        response = client.get(UPLOAD_URL)

    assert response.status_code == 200
    sql = " ".join(query["sql"].lower() for query in captured.captured_queries)
    assert "archive" not in sql


@requires_enterprise_upload
@pytest.mark.django_db
def test_sync_snapshot_query_selects_only_key_and_pack_revision(authenticated_user):
    from apps.system_mgmt.enterprise import provider_pack_sync
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client = _auth_client(authenticated_user, is_superuser=True)
    assert client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart").status_code == 201
    provider_registry.list()
    provider_pack_sync._last_check_at = 0.0

    with CaptureQueriesContext(connection) as captured:
        keys = {manifest.key for manifest in provider_registry.list()}

    assert "acme" in keys
    sql = " ".join(query["sql"].lower() for query in captured.captured_queries)
    assert "archive" not in sql
    assert "pack_revision" in sql
    assert "system_mgmt_uploadedproviderpack" in sql


@requires_enterprise_upload
@pytest.mark.django_db
def test_sync_cache_hit_does_not_read_archive(authenticated_user, monkeypatch):
    from apps.system_mgmt.enterprise import provider_pack_archive, provider_pack_sync
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client = _auth_client(authenticated_user, is_superuser=True)
    assert client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart").status_code == 201

    def fail_extract(*_args, **_kwargs):
        raise AssertionError("cache hit must not extract archive")

    monkeypatch.setattr(provider_pack_archive, "extract_provider_pack_zip", fail_extract)
    monkeypatch.setattr(provider_pack_sync, "extract_provider_pack_zip", fail_extract)
    provider_pack_sync.reset_sync_cache()
    loader.reset_builtin_providers()

    with CaptureQueriesContext(connection) as captured:
        keys = {manifest.key for manifest in provider_registry.list()}

    assert "acme" in keys
    sql = " ".join(query["sql"].lower() for query in captured.captured_queries)
    assert "archive" not in sql


@requires_enterprise_upload
@pytest.mark.django_db
def test_sync_only_pulls_when_revision_is_behind(authenticated_user, tmp_path, monkeypatch):
    from apps.system_mgmt.enterprise import provider_pack_sync

    client = _auth_client(authenticated_user, is_superuser=True)
    assert client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart").status_code == 201

    pulls = []
    original = provider_pack_sync._load_uploaded_packs_from_db

    def counting_load(snapshot=None):
        pulls.append("pull")
        return original(snapshot)

    monkeypatch.setattr(provider_pack_sync, "_load_uploaded_packs_from_db", counting_load)
    provider_pack_sync.reset_sync_cache()
    loader.reset_builtin_providers()
    provider_registry.list()
    provider_registry.list()

    assert pulls == ["pull"]


@requires_enterprise_upload
@pytest.mark.django_db
def test_sync_failure_keeps_builtin_providers(monkeypatch, caplog):
    from apps.system_mgmt.enterprise import provider_pack_sync

    def boom():
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr(provider_pack_sync, "_read_uploaded_pack_snapshot", boom)
    provider_pack_sync.reset_sync_cache()
    loader.reset_builtin_providers()

    with caplog.at_level(logging.WARNING, logger="system-manager"):
        keys = {manifest.key for manifest in provider_registry.list()}

    records = [
        record
        for record in caplog.records
        if record.name == "system-manager" and "provider_pack_sync_skipped" in record.msg
    ]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.msg == "event=provider_pack_sync_skipped failed_stage=snapshot error_type=%s"
    assert record.args == ("RuntimeError",)
    assert record.exc_info is not None
    formatted = logging.Formatter().format(record)
    assert "catalog unavailable" in formatted
    assert "event=provider_pack_sync_skipped failed_stage=snapshot error_type=RuntimeError" in formatted
    assert keys == {"ad", "feishu", "wechat", "wecom"}


@requires_enterprise_upload
@pytest.mark.django_db
def test_upload_audit_log_omits_archive(authenticated_user, tmp_path, caplog):
    client = _auth_client(authenticated_user, is_superuser=True)
    files = _minimal_pack_files("acmelog")
    files["acmelog/sentinel.bin"] = "ZIP-SENTINEL-CREDENTIAL-DO-NOT-LOG"
    padded = _zip_bytes(files)
    sentinel = b"ZIP-SENTINEL-CREDENTIAL-DO-NOT-LOG"

    with caplog.at_level(logging.INFO, logger="system-manager"):
        response = client.post(UPLOAD_URL, {"file": io.BytesIO(padded)}, format="multipart")

    assert response.status_code == 201
    records = [
        record
        for record in caplog.records
        if record.name == "system-manager" and "provider_pack_uploaded" in record.msg
    ]
    assert len(records) == 1
    record = records[0]
    assert record.msg == "event=provider_pack_uploaded pack_key=%s pack_revision=%s"
    assert record.args == ("acmelog", 1)
    assert sentinel not in record.getMessage().encode()
    logs = OperationLog.objects.filter(action_type="create", summary__contains="acmelog")
    assert logs.exists()
    for record in logs:
        assert sentinel not in str(record.summary).encode()
        assert "archive" not in (record.detail or {})
    assert sentinel not in caplog.text.encode()
    assert "archive" not in response.data


def _connection_summary(provider_key: str) -> str:
    from apps.system_mgmt.providers.registry import capability_adapter_registry

    adapter = capability_adapter_registry.get(f"{provider_key}.base_connection")
    assert adapter is not None
    result = adapter.test_connection(config={}, provider_key=provider_key, capability_key="base")
    return result.summary


@requires_enterprise_upload
@pytest.mark.django_db
def test_replace_true_overwrites_pack_and_resets_matching_instances(authenticated_user):
    from apps.system_mgmt.models import (
        IntegrationInstanceStatusChoices,
        LoginAuthBinding,
        LoginAuthBindingPlatformFieldChoices,
        LoginAuthBindingUnmatchedActionChoices,
        UploadedProviderPack,
    )
    from apps.system_mgmt.providers.registry import capability_adapter_registry

    client = _auth_client(authenticated_user, is_superuser=True)
    first = client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme", marker="v1", include_login_auth=True)))},
        format="multipart",
    )
    assert first.status_code == 201
    assert _connection_summary("acme") == "v1"

    kept_config = {"endpoint": "https://acme.example", "token": "keep-me"}
    instance = IntegrationInstance.objects.create(
        name="acme-prod",
        provider_key="acme",
        config=kept_config,
        team=[1],
        enabled=True,
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        capability_enabled={"login_auth": True},
    )
    binding = LoginAuthBinding.objects.create(
        name="acme-login",
        integration_instance=instance,
        enabled=True,
        external_field="user_id",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
    )
    wecom = IntegrationInstance.objects.create(
        name="wecom-prod",
        provider_key="wecom",
        config={"corp_id": "keep"},
        team=[1],
        enabled=True,
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        capability_enabled={"login_auth": True},
    )
    other_uploaded = client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("other", marker="other-v1")))},
        format="multipart",
    )
    assert other_uploaded.status_code == 201
    other_instance = IntegrationInstance.objects.create(
        name="other-prod",
        provider_key="other",
        config={"keep": True},
        team=[1],
        enabled=True,
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={},
    )

    replaced = client.post(
        UPLOAD_URL,
        {
            "file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme", marker="v2", include_login_auth=False))),
            "replace": "true",
        },
        format="multipart",
    )

    assert replaced.status_code == 200
    assert replaced.data["pack_revision"] == 2
    pack = UploadedProviderPack.objects.get(key="acme")
    assert pack.pack_revision == 2
    assert _connection_summary("acme") == "v2"
    assert capability_adapter_registry.get("acme.login_auth") is None

    instance.refresh_from_db()
    wecom.refresh_from_db()
    other_instance.refresh_from_db()
    assert instance.config == kept_config
    assert instance.status == IntegrationInstanceStatusChoices.PENDING_VERIFICATION
    assert instance.capability_status.get("login_auth") != IntegrationInstanceStatusChoices.READY
    assert all(
        value == IntegrationInstanceStatusChoices.PENDING_VERIFICATION
        for value in instance.capability_status.values()
    )
    assert LoginAuthBinding.objects.filter(pk=binding.pk).exists()
    assert wecom.status == IntegrationInstanceStatusChoices.READY
    assert wecom.capability_status == {"login_auth": IntegrationInstanceStatusChoices.READY}
    assert other_instance.status == IntegrationInstanceStatusChoices.READY
    assert _connection_summary("other") == "other-v1"

    available = client.get("/api/v1/system_mgmt/integration_instance/available_instances/?capability=login_auth")
    assert available.status_code == 200
    assert not any(item["id"] == instance.id for item in available.data)


@requires_enterprise_upload
@pytest.mark.django_db
def test_replace_trial_load_failure_keeps_old_pack_and_instances(authenticated_user, tmp_path, caplog):
    from apps.system_mgmt.models import (
        IntegrationInstanceStatusChoices,
        UploadedProviderPack,
    )

    client = _auth_client(authenticated_user, is_superuser=True)
    assert client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme", marker="v1")))},
        format="multipart",
    ).status_code == 201
    instance = IntegrationInstance.objects.create(
        name="acme-prod",
        provider_key="acme",
        config={"keep": "yes"},
        team=[1],
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
    )
    cache_root = Path(tmp_path / "provider-pack-cache")
    files = _minimal_pack_files("acme", marker="v2")
    files["acme/__init__.py"] = "raise RuntimeError('replace-boom')\n"
    files["acme/sentinel.bin"] = "ZIP-SENTINEL-CREDENTIAL-DO-NOT-LOG"
    sentinel = b"ZIP-SENTINEL-CREDENTIAL-DO-NOT-LOG"

    with caplog.at_level(logging.ERROR, logger="system-manager"):
        response = client.post(
            UPLOAD_URL,
            {"file": io.BytesIO(_zip_bytes(files)), "replace": "true"},
            format="multipart",
        )

    assert response.status_code == 400
    pack = UploadedProviderPack.objects.get(key="acme")
    assert pack.pack_revision == 1
    assert _connection_summary("acme") == "v1"
    instance.refresh_from_db()
    assert instance.status == IntegrationInstanceStatusChoices.READY
    assert instance.config == {"keep": "yes"}
    assert not (cache_root / "acme" / "2").exists() or not any((cache_root / "acme" / "2").rglob("*"))
    records = [
        record
        for record in caplog.records
        if record.name == "system-manager" and "provider_pack_upload_failed" in record.msg
    ]
    assert len(records) == 1
    assert records[0].args == ("acme", "trial_load", "RuntimeError")
    formatted = logging.Formatter().format(records[0])
    assert sentinel not in formatted.encode()


@requires_enterprise_upload
@pytest.mark.django_db
def test_replace_success_drops_previous_revision_cache(authenticated_user, tmp_path):
    client = _auth_client(authenticated_user, is_superuser=True)
    cache_root = Path(tmp_path / "provider-pack-cache")
    assert client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme", marker="v1")))},
        format="multipart",
    ).status_code == 201
    assert (cache_root / "acme" / "1").exists()

    replaced = client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme", marker="v2"))), "replace": "true"},
        format="multipart",
    )
    assert replaced.status_code == 200
    assert _connection_summary("acme") == "v2"
    assert not (cache_root / "acme" / "1").exists()
    assert (cache_root / "acme" / "2" / "__init__.py").is_file() or (
        cache_root / "acme" / "2" / "acme" / "__init__.py"
    ).is_file()


@requires_enterprise_upload
@pytest.mark.django_db
def test_stale_replace_loser_returns_409_without_second_reset(authenticated_user, monkeypatch):
    from apps.system_mgmt.enterprise.viewset import provider_pack_viewset
    from apps.system_mgmt.models import (
        IntegrationInstanceStatusChoices,
        UploadedProviderPack,
    )

    client = _auth_client(authenticated_user, is_superuser=True)
    assert client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme", marker="v1")))},
        format="multipart",
    ).status_code == 201
    assert client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme", marker="v2"))), "replace": "true"},
        format="multipart",
    ).status_code == 200
    instance = IntegrationInstance.objects.create(
        name="acme-prod",
        provider_key="acme",
        config={"keep": True},
        team=[1],
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
    )

    def stale_snapshot(key):
        row = UploadedProviderPack.objects.defer("archive").filter(key=key).first()
        if row is not None:
            row.pack_revision = 1
        return row

    monkeypatch.setattr(provider_pack_viewset, "snapshot_uploaded_pack", stale_snapshot)

    loser = client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme", marker="v3"))), "replace": "true"},
        format="multipart",
    )

    assert loser.status_code == 409
    assert loser.data["pack_revision"] == 2
    assert UploadedProviderPack.objects.get(key="acme").pack_revision == 2
    instance.refresh_from_db()
    assert instance.status == IntegrationInstanceStatusChoices.READY
    assert _connection_summary("acme") == "v2"


def _pack_url(key: str) -> str:
    return f"{UPLOAD_URL}{key}/"


def _corrupt_uploaded_pack_archive(key: str) -> None:
    import shutil

    from apps.system_mgmt.enterprise import provider_pack_sync
    from apps.system_mgmt.enterprise.provider_pack_archive import get_provider_pack_cache_dir
    from apps.system_mgmt.models import UploadedProviderPack

    pack = UploadedProviderPack.objects.get(key=key)
    pack.archive = b"not-a-zip"
    pack.save(update_fields=["archive", "updated_at"])
    shutil.rmtree(get_provider_pack_cache_dir() / key, ignore_errors=True)
    provider_pack_sync.reset_sync_cache()
    loader.reset_builtin_providers()


@requires_enterprise_upload
@pytest.mark.django_db
def test_uninstall_rejected_when_instances_exist(authenticated_user):
    client = _auth_client(authenticated_user, is_superuser=True)
    assert client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart").status_code == 201
    IntegrationInstance.objects.create(name="acme-prod", provider_key="acme", config={}, team=[1])

    response = client.delete(_pack_url("acme"))

    assert response.status_code == 409
    assert response.data["instance_count"] == 1
    assert "instance" in response.data["message"].lower() or "实例" in str(response.data["message"])
    from apps.system_mgmt.models import UploadedProviderPack

    assert UploadedProviderPack.objects.filter(key="acme").exists()
    assert provider_registry.get("acme") is not None
    assert "acme" in {item["key"] for item in client.get(PROVIDERS_URL).data}


@requires_enterprise_upload
@pytest.mark.django_db
def test_uninstall_without_instances_removes_pack_from_list_and_create_candidates(
    authenticated_user, tmp_path, caplog
):
    from apps.system_mgmt.models import UploadedProviderPack

    client = _auth_client(authenticated_user, is_superuser=True)
    cache_root = Path(tmp_path / "provider-pack-cache")
    assert client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart").status_code == 201

    with caplog.at_level(logging.INFO, logger="system-manager"):
        response = client.delete(_pack_url("acme"))

    assert response.status_code == 200
    records = [
        record
        for record in caplog.records
        if record.name == "system-manager" and "provider_pack_uninstalled" in record.msg
    ]
    assert len(records) == 1
    assert records[0].msg == "event=provider_pack_uninstalled pack_key=%s pack_revision=%s"
    assert records[0].args == ("acme", 1)
    assert not UploadedProviderPack.objects.filter(key="acme").exists()
    assert provider_registry.get("acme") is None
    listed = {item["key"]: item for item in client.get(UPLOAD_URL).data}
    assert "acme" not in listed
    assert "wecom" in listed
    assert "acme" not in {item["key"] for item in client.get(PROVIDERS_URL).data}
    assert not (cache_root / "acme").exists() or not any((cache_root / "acme").rglob("*"))


@requires_enterprise_upload
@pytest.mark.django_db
def test_uninstall_builtin_key_is_rejected(authenticated_user):
    client = _auth_client(authenticated_user, is_superuser=True)
    response = client.delete(_pack_url("wecom"))
    assert response.status_code == 400
    assert provider_registry.get("wecom") is not None


@requires_enterprise_upload
@pytest.mark.django_db
def test_uninstall_without_delete_permission_returns_403(authenticated_user):
    client = _auth_client(authenticated_user, is_superuser=True)
    assert client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart").status_code == 201
    other = _auth_client(authenticated_user, is_superuser=False)
    response = other.delete(_pack_url("acme"))
    assert response.status_code == 403
    from apps.system_mgmt.models import UploadedProviderPack

    assert UploadedProviderPack.objects.filter(key="acme").exists()


@requires_enterprise_upload
@pytest.mark.django_db
def test_failed_uploaded_pack_is_listed_but_not_a_create_candidate(authenticated_user, caplog):
    client = _auth_client(authenticated_user, is_superuser=True)
    assert client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart").status_code == 201

    with caplog.at_level(logging.ERROR, logger="system-manager"):
        _corrupt_uploaded_pack_archive("acme")
        pack_list = client.get(UPLOAD_URL)
        providers = client.get(PROVIDERS_URL)

    assert pack_list.status_code == 200
    listed = {item["key"]: item for item in pack_list.data}
    assert listed["acme"]["source"] == "uploaded"
    assert listed["acme"]["load_status"] == "failed"
    assert listed["acme"]["error_type"]
    assert listed["acme"]["error_type"] != ""
    assert "ZIP-SENTINEL" not in str(listed["acme"])
    assert listed["wecom"]["load_status"] == "loaded"
    assert listed["wecom"]["source"] == "builtin"
    assert "acme" not in {item["key"] for item in providers.data}
    records = [
        record
        for record in caplog.records
        if record.name == "system-manager" and "provider_pack_sync_failed" in record.msg
    ]
    assert records
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    assert record.msg == "event=provider_pack_sync_failed pack_key=%s failed_stage=import error_type=%s"
    assert record.args == ("acme", "ValueError")
    assert record.exc_info is not None
    assert record.exc_info[0] is ValueError
    traceback_errors = [
        item
        for item in caplog.records
        if item.name == "system-manager" and item.levelno == logging.ERROR and item.exc_info
    ]
    assert traceback_errors == [record]
    formatted = logging.Formatter().format(record)
    assert b"not-a-zip" not in formatted.encode()


@requires_enterprise_upload
@pytest.mark.django_db
def test_failed_pack_instance_can_be_updated_but_test_connection_is_unavailable(authenticated_user):
    client = _auth_client(authenticated_user, is_superuser=True)
    authenticated_user.permission = {
        "system-manager": {"integration_center-Add", "integration_center-View", "integration_center-Edit"}
    }
    authenticated_user.save(update_fields=["is_superuser"])
    assert client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart").status_code == 201
    instance = IntegrationInstance.objects.create(
        name="acme-prod",
        provider_key="acme",
        config={"endpoint": "https://acme.example"},
        team=[1],
    )
    _corrupt_uploaded_pack_archive("acme")

    updated = client.put(
        f"/api/v1/system_mgmt/integration_instance/{instance.id}/",
        {
            "name": "acme-prod-renamed",
            "provider_key": "acme",
            "description": "keep-editing",
            "config": {"endpoint": "https://acme.example", "note": "updated"},
            "enabled": True,
            "team": [1],
            "status": instance.status,
            "capability_status": instance.capability_status,
            "capability_enabled": instance.capability_enabled,
        },
        format="json",
    )
    assert updated.status_code == 200
    instance.refresh_from_db()
    assert instance.name == "acme-prod-renamed"
    assert instance.config.get("note") == "updated"

    tested = client.post(
        f"/api/v1/system_mgmt/integration_instance/{instance.id}/test_connection/",
        {},
        format="json",
    )
    assert tested.status_code == 200
    payload = tested.data["data"]["data"]
    assert tested.data["data"]["result"] is False
    assert payload["errors"][0]["code"] == "provider.unavailable"
    assert "unavailable" in payload["summary"].lower() or "不可用" in payload["summary"]
    assert "Traceback" not in str(tested.data)
    assert "ValueError" not in payload["summary"]


@requires_enterprise_upload
@pytest.mark.django_db
def test_failed_pack_without_instances_can_be_uninstalled(authenticated_user):
    from apps.system_mgmt.models import UploadedProviderPack

    client = _auth_client(authenticated_user, is_superuser=True)
    assert client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart").status_code == 201
    _corrupt_uploaded_pack_archive("acme")
    listed = {item["key"]: item for item in client.get(UPLOAD_URL).data}
    assert listed["acme"]["load_status"] == "failed"

    response = client.delete(_pack_url("acme"))
    assert response.status_code == 200
    assert not UploadedProviderPack.objects.filter(key="acme").exists()
    assert "acme" not in {item["key"] for item in client.get(UPLOAD_URL).data}
