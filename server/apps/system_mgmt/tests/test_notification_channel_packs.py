import io
import logging

import pytest
from rest_framework.test import APIClient

from apps.core.logger import SafeLogException
from apps.system_mgmt.models import Channel, UploadedProviderPack
from apps.system_mgmt.providers import loader
from apps.system_mgmt.providers.registry import capability_adapter_registry, provider_registry
from apps.system_mgmt.services.notification_channel_pack import runtime_pack_config, send_loaded_notification_channel
from apps.system_mgmt.tests.test_provider_pack_upload import (
    UPLOAD_URL,
    _auth_client,
    _corrupt_uploaded_pack_archive,
    _drop_uploaded_import_trees,
    _minimal_pack_files,
    _zip_bytes,
    requires_enterprise_upload,
)

PROVIDERS_URL = "/api/v1/system_mgmt/integration_instance/providers/"
CHANNEL_URL = "/api/v1/system_mgmt/channel/"
INSTANCE_URL = "/api/v1/system_mgmt/integration_instance/"
_PACK_FAILED = "event=notification_channel_pack_failed channel_id=%s failed_stage=%s error_type=%s"
_PACK_FINISHED = "event=notification_channel_pack_finished channel_id=%s accepted=%s unknown=%s"
_PURPOSE_UNREADABLE = "event=provider_pack_purpose_unreadable pack_key=%s failed_stage=read_archive error_type=%s"
_SECRET = "pack-secret-sentinel"
_PHONE = "15500001111"
_TITLE = "标题-sentinel"
_BODY = "正文-sentinel"
_ARCHIVE_SENTINEL = b"archive-secret-sentinel"


@pytest.fixture(autouse=True)
def clean_provider_state(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVIDER_PACK_CACHE_DIR", str(tmp_path / "provider-pack-cache"))
    loader.reset_builtin_providers()
    _drop_uploaded_import_trees()
    yield
    loader.reset_builtin_providers()
    _drop_uploaded_import_trees()


def _language(name: str) -> str:
    return f"name: {name}\ndescription: {name} notification channel.\n"


def _channel_pack_files(key: str, *, delivery: str, parameter_mode: str | None = None, extra: dict | None = None) -> dict[str, str]:
    mode_line = f'                "parameter_mode": "{parameter_mode}",\n' if parameter_mode else ""
    files = {
        f"{key}/__init__.py": "from .manifest import PROVIDER_MANIFEST\n",
        f"{key}/manifest.py": (
            "from apps.system_mgmt.providers.schemas import ProviderManifest\n\n"
            "PROVIDER_MANIFEST = ProviderManifest.model_validate(\n"
            "    {\n"
            f'        "key": "{key}",\n'
            f'        "name": "{key.title()}",\n'
            '        "description": "pack channel",\n'
            '        "instance_templates": {\n'
            '            "connection": {\n'
            '                "title": "Connection",\n'
            '                "groups": [{\n'
            '                    "key": "main",\n'
            '                    "title": "Main",\n'
            '                    "fields": [\n'
            '                        {"key": "endpoint", "label": "Endpoint", "required": True},\n'
            '                        {"key": "api_secret", "label": "Secret", "required": True, "secret": True},\n'
            '                        {"key": "template_id", "label": "Template", "required": False}\n'
            "                    ]\n"
            "                }]\n"
            "            }\n"
            "        },\n"
            '        "capabilities": [{\n'
            '                "key": "notification_channel",\n'
            '                "name": "Notify",\n'
            f'                "adapter_key": "{key}.send",\n'
            '                "adapter_path": "adapters.send.PackSendAdapter",\n'
            f'                "delivery": "{delivery}",\n'
            f"{mode_line}"
            "        }]\n"
            "    }\n"
            ")\n"
        ),
        f"{key}/language/en.yaml": _language(key.title()),
        f"{key}/language/zh-Hans.yaml": _language(key.title()),
        f"{key}/adapters/__init__.py": "",
        f"{key}/adapters/send.py": (
            "class PackSendAdapter:\n"
            "    hook = None\n"
            "    calls = []\n"
            "    @classmethod\n"
            "    def send(cls, *args):\n"
            "        cls.calls.append(args)\n"
            "        if cls.hook is not None:\n"
            "            return cls.hook(*args)\n"
            '        return {"status": "accepted", "request_id": "req-1", "reason": ""}\n'
        ),
    }
    if extra:
        files.update(extra)
    return files


def _upload(client, key, **kwargs):
    files = _channel_pack_files(key, **{name: kwargs.pop(name) for name in ("delivery", "parameter_mode") if name in kwargs})
    payload = {"file": io.BytesIO(_zip_bytes(files))}
    if "purpose" in kwargs:
        payload["purpose"] = kwargs.pop("purpose")
    if kwargs.get("replace"):
        payload["replace"] = "true"
    return client.post(UPLOAD_URL, payload, format="multipart")


def _client(user) -> APIClient:
    return _auth_client(
        user,
        is_superuser=True,
        permissions={
            "integration_center-Add",
            "integration_center-View",
            "integration_center-Edit",
            "integration_center-Delete",
            "channel_list-Add",
            "channel_list-View",
            "channel_list-Edit",
        },
    )


def _adapter(key):
    return capability_adapter_registry.get(f"{key}.send")


def _channel_payload(channel_type, *, endpoint, secret, template_id="", parameters=None, name="渠道甲"):
    config = {"endpoint": endpoint, "api_secret": secret, "template_id": template_id}
    if parameters is not None:
        config["parameters"] = parameters
    return {
        "name": name,
        "channel_type": channel_type,
        "description": "pack channel",
        "team": [1],
        "config": config,
    }


def _sys_user(phone):
    from apps.system_mgmt.models import User

    return User.objects.create(
        username="testuser",
        display_name="Tester",
        email="tester@example.com",
        phone=phone,
        password="x",
        domain="domain.com",
    )


@requires_enterprise_upload
@pytest.mark.django_db
def test_upload_template_and_body_packs_and_two_instances_each(authenticated_user):
    client = _client(authenticated_user)
    assert _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    assert _upload(client, "bodypack", delivery="body", purpose="notification_channel").status_code == 201

    listed = {item["key"]: item for item in client.get(UPLOAD_URL).data}
    assert listed["tplpack"]["purpose"] == "notification_channel"
    assert listed["bodypack"]["purpose"] == "notification_channel"
    assert listed["wecom"]["purpose"] == "integration"

    packs = client.get(f"{CHANNEL_URL}notification_channel_packs/")
    assert packs.status_code == 200
    by_key = {item["key"]: item for item in packs.data}
    assert by_key["tplpack"]["delivery"] == "template"
    assert by_key["tplpack"]["instance_template"]
    assert by_key["bodypack"]["delivery"] == "body"

    created = []
    for channel_type, endpoints in (
        ("tplpack", ("https://a.example", "https://b.example")),
        ("bodypack", ("https://c.example", "https://d.example")),
    ):
        for index, endpoint in enumerate(endpoints):
            response = client.post(
                CHANNEL_URL,
                _channel_payload(
                    channel_type,
                    endpoint=endpoint,
                    secret=f"secret-{channel_type}-{index}",
                    template_id=f"T{index}",
                    parameters=[{"source": "content", "name": "", "value": ""}] if channel_type == "tplpack" else None,
                    name=f"{channel_type}-{index}",
                ),
                format="json",
            )
            assert response.status_code == 201, response.data
            assert response.data["config"]["api_secret"].startswith("******")
            assert "secret-" not in response.data["config"]["api_secret"]
            created.append(response.data)

    assert Channel.objects.filter(channel_type="tplpack").count() == 2
    assert Channel.objects.filter(channel_type="bodypack").count() == 2
    endpoints = {row.config.get("endpoint") for row in Channel.objects.filter(channel_type__in=["tplpack", "bodypack"])}
    assert endpoints == {"https://a.example", "https://b.example", "https://c.example", "https://d.example"}
    assert len(created) == 4


@requires_enterprise_upload
@pytest.mark.django_db
def test_missing_purpose_stays_integration_and_crossed_purpose_is_not_stored(authenticated_user):
    client = _client(authenticated_user)
    integration = client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("acme")))}, format="multipart")
    assert integration.status_code == 201
    listed = {item["key"]: item for item in client.get(UPLOAD_URL).data}
    assert listed["acme"]["purpose"] == "integration"

    channel_as_integration = client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_channel_pack_files("tplpack", delivery="template", parameter_mode="ordered"))), "purpose": "integration"},
        format="multipart",
    )
    assert channel_as_integration.status_code == 400
    assert not UploadedProviderPack.objects.filter(key="tplpack").exists()

    integration_as_channel = client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("other"))), "purpose": "notification_channel"},
        format="multipart",
    )
    assert integration_as_channel.status_code == 400
    assert not UploadedProviderPack.objects.filter(key="other").exists()

    disguised = _channel_pack_files("hybrid", delivery="template", parameter_mode="ordered")
    disguised.update(_minimal_pack_files("hybrid"))
    disguised["hybrid/manifest.py"] = _channel_pack_files("hybrid", delivery="template", parameter_mode="ordered")["hybrid/manifest.py"]
    crossed = client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(disguised)), "purpose": "integration"}, format="multipart")
    assert crossed.status_code == 400
    assert not UploadedProviderPack.objects.filter(key="hybrid").exists()


@requires_enterprise_upload
@pytest.mark.django_db
def test_reserved_key_and_dependency_file_are_rejected(authenticated_user):
    client = _client(authenticated_user)
    reserved = client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_channel_pack_files("email", delivery="body"))), "purpose": "notification_channel"},
        format="multipart",
    )
    assert reserved.status_code == 400
    assert not UploadedProviderPack.objects.filter(key="email").exists()

    with_dep = _channel_pack_files("deptpack", delivery="body", extra={"deptpack/requirements.txt": "requests\n"})
    rejected = client.post(UPLOAD_URL, {"file": io.BytesIO(_zip_bytes(with_dep)), "purpose": "notification_channel"}, format="multipart")
    assert rejected.status_code == 400
    assert not UploadedProviderPack.objects.filter(key="deptpack").exists()


@requires_enterprise_upload
@pytest.mark.django_db
def test_reload_classifies_channel_pack_from_manifest(authenticated_user):
    client = _client(authenticated_user)
    assert _upload(client, "tplpack", delivery="template", parameter_mode="named", purpose="notification_channel").status_code == 201
    loader.reset_builtin_providers()
    assert "tplpack" in {manifest.key for manifest in provider_registry.list()}
    listed = {item["key"]: item for item in client.get(UPLOAD_URL).data}
    assert listed["tplpack"]["purpose"] == "notification_channel"
    assert listed["tplpack"]["load_status"] == "loaded"
    _corrupt_uploaded_pack_archive("tplpack")
    failed = {item["key"]: item for item in client.get(UPLOAD_URL).data}
    assert failed["tplpack"]["purpose"] is None
    assert failed["tplpack"]["load_status"] == "failed"


@requires_enterprise_upload
@pytest.mark.django_db
def test_secret_mask_round_trip_keeps_ciphertext_when_masked(authenticated_user):
    client = _client(authenticated_user)
    assert _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    created = client.post(
        CHANNEL_URL,
        _channel_payload("tplpack", endpoint="https://a.example", secret="super-secret-value", parameters=[{"source": "title", "value": ""}]),
        format="json",
    )
    assert created.status_code == 201
    channel = Channel.objects.get(id=created.data["id"])
    assert runtime_pack_config(channel, provider_registry.get("tplpack"))["api_secret"] == "super-secret-value"
    assert created.data["config"]["api_secret"] == "******alue"

    masked = client.get(f"{CHANNEL_URL}{channel.id}/").data
    renamed = client.put(
        f"{CHANNEL_URL}{channel.id}/",
        {
            "name": "渠道乙",
            "channel_type": "tplpack",
            "description": "pack channel",
            "team": [1],
            "config": masked["config"],
        },
        format="json",
    )
    assert renamed.status_code == 200, renamed.data
    channel.refresh_from_db()
    assert runtime_pack_config(channel, provider_registry.get("tplpack"))["api_secret"] == "super-secret-value"

    changed = dict(masked["config"])
    changed["endpoint"] = "https://changed.example"
    updated = client.put(
        f"{CHANNEL_URL}{channel.id}/",
        {
            "name": "渠道乙",
            "channel_type": "tplpack",
            "description": "pack channel",
            "team": [1],
            "config": changed,
        },
        format="json",
    )
    assert updated.status_code == 200, updated.data
    channel.refresh_from_db()
    assert channel.config["endpoint"] == "https://changed.example"
    assert runtime_pack_config(channel, provider_registry.get("tplpack"))["api_secret"] == "super-secret-value"


@requires_enterprise_upload
@pytest.mark.django_db
def test_named_parameters_require_names_and_ordered_does_not(authenticated_user):
    client = _client(authenticated_user)
    assert _upload(client, "namedpack", delivery="template", parameter_mode="named", purpose="notification_channel").status_code == 201
    missing = client.post(
        CHANNEL_URL,
        _channel_payload(
            "namedpack", endpoint="https://a.example", secret="secret-value", parameters=[{"source": "content", "name": "", "value": ""}]
        ),
        format="json",
    )
    assert missing.status_code == 400
    assert _upload(client, "orderedpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    ordered = client.post(
        CHANNEL_URL,
        _channel_payload("orderedpack", endpoint="https://a.example", secret="secret-value", parameters=[{"source": "literal", "value": "fixed"}]),
        format="json",
    )
    assert ordered.status_code == 201, ordered.data


@requires_enterprise_upload
@pytest.mark.django_db
def test_send_contract_calls_the_pack_without_a_prior_test_and_does_not_retry(authenticated_user):
    client = _client(authenticated_user)
    _sys_user("+44 7700 900123")
    from apps.system_mgmt.models import User

    other = User.objects.create(
        username="nophone",
        display_name="No Phone",
        email="nophone@example.com",
        phone="",
        password="x",
        domain="domain.com",
    )
    assert _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    created = client.post(
        CHANNEL_URL,
        _channel_payload(
            "tplpack",
            endpoint="https://a.example",
            secret="secret-value",
            parameters=[{"source": "title", "value": ""}, {"source": "literal", "value": "code"}],
        ),
        format="json",
    )
    channel = Channel.objects.get(id=created.data["id"])
    adapter = _adapter("tplpack")
    adapter.calls.clear()

    sent_first = send_loaded_notification_channel(channel, "Hello", "Body", [_sys_user_id()])
    assert sent_first["result"] is True
    assert sent_first["retryable"] is False
    assert adapter.calls[-1][1] == "+44 7700 900123"
    adapter.calls.clear()

    accepted = client.post(
        f"{CHANNEL_URL}test_send/",
        {"channel_id": channel.id, "channel_type": "tplpack", "title": "Hello", "content": "Body"},
        format="json",
    )
    assert accepted.status_code == 200, accepted.data
    assert adapter.calls[-1][1] == "+44 7700 900123"
    assert adapter.calls[-1][2] == ["[渠道甲] Test Message", "code"]

    adapter.calls.clear()
    sent = send_loaded_notification_channel(channel, "Hello", "Body", [channel_user_id(), other.id])
    assert sent["result"] is False
    assert sent["retryable"] is False
    assert len(adapter.calls) == 1
    assert "没有电话" in sent["message"]

    adapter.hook = lambda *args: {"status": "unknown", "request_id": "u-1", "reason": ""}
    adapter.calls.clear()
    unknown = send_loaded_notification_channel(channel, "Hello", "Body", [channel_user_id()])
    assert unknown["result"] is False
    assert unknown["retryable"] is False
    assert len(adapter.calls) == 1
    adapter.calls.clear()
    send_loaded_notification_channel(channel, "Hello", "Body", [channel_user_id()])
    assert len(adapter.calls) == 1

    adapter.hook = lambda *args: {"status": "rejected", "request_id": "r-1", "reason": "bad number"}
    failed = client.post(
        f"{CHANNEL_URL}test_send/",
        {"channel_id": channel.id, "channel_type": "tplpack", "title": "Hello", "content": "Body"},
        format="json",
    )
    assert failed.status_code == 400
    calls_before = len(adapter.calls)
    refused = send_loaded_notification_channel(channel, "Hello", "Body", [channel_user_id()])
    assert refused["result"] is False
    assert refused["retryable"] is False
    assert len(adapter.calls) == calls_before + 1


def _log_blob(*parts) -> str:
    return "\n".join(str(part) for part in parts)


def _sentinels_absent(blob: str) -> None:
    for sentinel in (_SECRET, _PHONE, _TITLE, _BODY, _ARCHIVE_SENTINEL.decode()):
        assert sentinel not in blob


@requires_enterprise_upload
@pytest.mark.django_db
def test_pack_send_exception_logs_one_sanitized_error(authenticated_user, caplog):
    client = _client(authenticated_user)
    assert _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    created = client.post(
        CHANNEL_URL,
        _channel_payload("tplpack", endpoint="https://sms.example/send", secret=_SECRET, template_id="SMS_1"),
        format="json",
    )
    channel = Channel.objects.get(id=created.data["id"])
    user = _sys_user(_PHONE)
    caught = {}

    def explode(config, phone, parameters):
        error = RuntimeError(f"{config['api_secret']} {phone} {_TITLE} {_BODY}")
        caught["error"] = error
        raise error

    adapter = _adapter("tplpack")
    adapter.hook = explode
    with caplog.at_level(logging.DEBUG, logger="system-manager"):
        result = send_loaded_notification_channel(channel, _TITLE, _BODY, [user.id])

    error = caught["error"]
    assert str(error) == f"{_SECRET} {_PHONE} {_TITLE} {_BODY}"
    assert result["result"] is False
    assert result["retryable"] is False
    assert result["recipients"] == [{"user_id": user.id, "status": "unknown", "request_id": "", "reason": "发送结果未知"}]
    assert _SECRET not in result["message"]
    failed = [record for record in caplog.records if record.msg == _PACK_FAILED]
    assert len(failed) == 1
    record = failed[0]
    assert record.levelno == logging.ERROR
    assert record.args == (channel.id, "call_pack", "RuntimeError")
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[1] is not error
    assert record.exc_info[2] is error.__traceback__
    formatted = logging.Formatter("%(levelname)s %(message)s").format(record)
    _sentinels_absent(_log_blob(record.getMessage(), formatted, caplog.text))
    assert [item for item in caplog.records if item.msg == _PACK_FINISHED] == []
    assert sum(item.levelno == logging.ERROR for item in caplog.records) == 1


@requires_enterprise_upload
@pytest.mark.django_db
def test_pack_send_success_logs_finished_without_error(authenticated_user, caplog):
    client = _client(authenticated_user)
    assert _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    created = client.post(
        CHANNEL_URL,
        _channel_payload("tplpack", endpoint="https://sms.example/send", secret=_SECRET, template_id="SMS_1"),
        format="json",
    )
    channel = Channel.objects.get(id=created.data["id"])
    user = _sys_user(_PHONE)
    with caplog.at_level(logging.DEBUG, logger="system-manager"):
        result = send_loaded_notification_channel(channel, _TITLE, _BODY, [user.id])

    assert result["result"] is True
    assert result["retryable"] is False
    assert result["recipients"][0]["status"] == "accepted"
    finished = [record for record in caplog.records if record.msg == _PACK_FINISHED]
    assert len(finished) == 1
    record = finished[0]
    assert record.levelno == logging.INFO
    assert record.args == (channel.id, 1, 0)
    assert record.getMessage() == f"event=notification_channel_pack_finished channel_id={channel.id} accepted=1 unknown=0"
    formatted = logging.Formatter("%(levelname)s %(message)s").format(record)
    _sentinels_absent(_log_blob(record.getMessage(), formatted, caplog.text))
    assert not any(item.levelno >= logging.ERROR for item in caplog.records)


@requires_enterprise_upload
@pytest.mark.django_db
def test_unreadable_archive_logs_purpose_without_the_bytes(authenticated_user, caplog):
    from apps.system_mgmt.enterprise.viewset.provider_pack_viewset import _manifest_from_archive
    from apps.system_mgmt.models import UploadedProviderPack

    client = _client(authenticated_user)
    assert _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    pack = UploadedProviderPack.objects.get(key="tplpack")
    pack.archive = b"not-a-zip-" + _ARCHIVE_SENTINEL
    pack.save(update_fields=["archive", "updated_at"])
    pack.refresh_from_db()

    with caplog.at_level(logging.DEBUG, logger="system-manager"):
        assert _manifest_from_archive(pack) is None

    records = [record for record in caplog.records if record.msg == _PURPOSE_UNREADABLE]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.DEBUG
    assert record.args == ("tplpack", "ValueError")
    assert record.exc_info is None
    assert record.getMessage() == "event=provider_pack_purpose_unreadable pack_key=tplpack failed_stage=read_archive error_type=ValueError"
    formatted = logging.Formatter("%(levelname)s %(message)s").format(record)
    _sentinels_absent(_log_blob(record.getMessage(), formatted, caplog.text))
    assert not any(item.levelno >= logging.ERROR for item in caplog.records)
    assert UploadedProviderPack.objects.get(key="tplpack").archive == b"not-a-zip-" + _ARCHIVE_SENTINEL


def _sys_user_id():
    from apps.system_mgmt.models import User

    return User.objects.get(username="testuser", domain="domain.com").id


def channel_user_id():
    return _sys_user_id()


@requires_enterprise_upload
@pytest.mark.django_db
def test_body_pack_sends_title_and_body_once(authenticated_user):
    client = _client(authenticated_user)
    assert _upload(client, "bodypack", delivery="body", purpose="notification_channel").status_code == 201
    created = client.post(
        CHANNEL_URL,
        _channel_payload("bodypack", endpoint="https://hook.example", secret="body-secret"),
        format="json",
    )
    channel = Channel.objects.get(id=created.data["id"])
    adapter = _adapter("bodypack")
    adapter.calls.clear()
    result = send_loaded_notification_channel(channel, "Title", "Rendered body", [1, 2])
    assert result["result"] is True
    assert len(adapter.calls) == 1
    assert adapter.calls[0][1:] == ("Title", "Rendered body")
    assert adapter.calls[0][0]["api_secret"] == "body-secret"
    adapter.calls.clear()
    tested = client.post(
        f"{CHANNEL_URL}test_send/",
        {"channel_id": channel.id, "channel_type": "bodypack", "title": "不会使用", "content": "不会使用"},
        format="json",
    )
    assert tested.status_code == 200, tested.data
    assert adapter.calls[0][1:] == (
        "[渠道甲] Test Message",
        "This is a test message from channel '渠道甲'. Receiver: testuser",
    )


@requires_enterprise_upload
@pytest.mark.django_db
def test_incomplete_secret_and_unloaded_pack_do_not_call_send(authenticated_user):
    client = _client(authenticated_user)
    assert _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    created = client.post(
        CHANNEL_URL,
        _channel_payload("tplpack", endpoint="https://a.example", secret="secret-value", parameters=[{"source": "content", "value": ""}]),
        format="json",
    )
    channel = Channel.objects.get(id=created.data["id"])
    channel.config["api_secret"] = "gAAAA-not-a-token"
    channel.save(update_fields=["config"])
    adapter = _adapter("tplpack")
    adapter.calls.clear()
    unread = send_loaded_notification_channel(channel, "Hello", "Body", [1])
    assert unread["result"] is False
    assert unread["retryable"] is False
    assert adapter.calls == []

    channel.config["parameters"] = [{"source": "nope"}]
    channel.config["api_secret"] = created.data["config"]["api_secret"]
    channel.save(update_fields=["config"])
    invalid = send_loaded_notification_channel(channel, "Hello", "Body", [1])
    assert invalid["retryable"] is False
    assert adapter.calls == []

    missing = Channel.objects.create(name="gone", channel_type="missingpack", description="x", team=[1], config={})
    unloaded = send_loaded_notification_channel(missing, "Hello", "Body", [1])
    assert unloaded["result"] is False
    assert unloaded["retryable"] is False
    assert "未加载" in unloaded["message"]


@requires_enterprise_upload
@pytest.mark.django_db
def test_replace_keeps_channel_config_and_blocks_delivery_change_and_uninstall(authenticated_user):
    client = _client(authenticated_user)
    assert _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    created = client.post(
        CHANNEL_URL,
        _channel_payload("tplpack", endpoint="https://a.example", secret="secret-value", parameters=[{"source": "content", "value": ""}]),
        format="json",
    )
    channel = Channel.objects.get(id=created.data["id"])

    changed = client.post(
        UPLOAD_URL,
        {
            "file": io.BytesIO(_zip_bytes(_channel_pack_files("tplpack", delivery="body"))),
            "purpose": "notification_channel",
            "replace": "true",
        },
        format="multipart",
    )
    assert changed.status_code == 409
    channel.refresh_from_db()
    assert channel.config["endpoint"] == "https://a.example"
    assert provider_registry.get("tplpack").get_capability("notification_channel").delivery == "template"

    replaced = client.post(
        UPLOAD_URL,
        {
            "file": io.BytesIO(_zip_bytes(_channel_pack_files("tplpack", delivery="template", parameter_mode="named"))),
            "purpose": "notification_channel",
            "replace": "true",
        },
        format="multipart",
    )
    assert replaced.status_code == 200, replaced.data
    channel.refresh_from_db()
    assert channel.config["endpoint"] == "https://a.example"
    assert provider_registry.get("tplpack").get_capability("notification_channel").parameter_mode == "named"
    sent = send_loaded_notification_channel(channel, "Hello", "Body", [1])
    assert sent["result"] is False
    assert sent["retryable"] is False
    assert "不完整" in sent["message"]
    assert _adapter("tplpack").calls == []

    mismatch = client.post(
        UPLOAD_URL,
        {"file": io.BytesIO(_zip_bytes(_minimal_pack_files("tplpack"))), "purpose": "integration", "replace": "true"},
        format="multipart",
    )
    assert mismatch.status_code == 400

    uninstall = client.delete(f"{UPLOAD_URL}{channel.channel_type}/")
    assert uninstall.status_code == 409
    channel.delete()
    assert client.delete(f"{UPLOAD_URL}tplpack/").status_code == 200


@requires_enterprise_upload
@pytest.mark.django_db
def test_unreadable_pack_can_be_replaced_on_the_selected_path(authenticated_user):
    client = _client(authenticated_user)
    assert _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    _corrupt_uploaded_pack_archive("tplpack")

    replaced = _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel", replace=True)

    assert replaced.status_code == 200, replaced.data
    assert provider_registry.get("tplpack").get_capability("notification_channel").delivery == "template"


@requires_enterprise_upload
@pytest.mark.django_db
def test_unreadable_pack_with_channels_rejects_replace(authenticated_user):
    from apps.system_mgmt.models import UploadedProviderPack

    client = _client(authenticated_user)
    assert _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    created = client.post(
        CHANNEL_URL,
        _channel_payload("tplpack", endpoint="https://a.example", secret="secret-value", parameters=[{"source": "content", "value": ""}]),
        format="json",
    )
    channel = Channel.objects.get(id=created.data["id"])
    _corrupt_uploaded_pack_archive("tplpack")

    replaced = _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel", replace=True)

    assert replaced.status_code == 409
    assert replaced.data["reason"] == "delivery_changed"
    channel.refresh_from_db()
    assert channel.config["endpoint"] == "https://a.example"
    assert UploadedProviderPack.objects.get(key="tplpack").archive == b"not-a-zip"
    assert provider_registry.get("tplpack") is None


@requires_enterprise_upload
@pytest.mark.django_db
def test_integration_instance_create_rejects_notification_channel_pack(authenticated_user):
    client = _client(authenticated_user)
    assert _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    providers = client.get(PROVIDERS_URL)
    assert "tplpack" not in {item["key"] for item in providers.data}
    created = client.post(
        INSTANCE_URL,
        {"name": "nope", "provider_key": "tplpack", "description": "no", "config": {}, "team": [1]},
        format="json",
    )
    assert created.status_code == 400
    from apps.system_mgmt.models import IntegrationInstance

    assert not IntegrationInstance.objects.filter(provider_key="tplpack").exists()


@requires_enterprise_upload
@pytest.mark.django_db
def test_workflow_returns_output_for_non_retryable_pack_failure(authenticated_user, monkeypatch):
    from apps.workflow.atom_packages.bklite_notification.runtime import handler

    client = _client(authenticated_user)
    assert _upload(client, "tplpack", delivery="template", parameter_mode="ordered", purpose="notification_channel").status_code == 201
    channel = Channel.objects.create(
        name="流程渠道",
        channel_type="tplpack",
        description="pack",
        team=[1],
        config={"endpoint": "https://a.example", "api_secret": "x"},
    )

    class FakeMgmt:
        def dispatch_notification(self, **kwargs):
            return {"result": False, "retryable": False, "message": "渠道拒绝发送"}

    monkeypatch.setattr(handler, "SystemMgmt", lambda: FakeMgmt())
    output = handler.execute(
        {
            "__bklite_context": {"organization_id": 1, "execution_id": "ex-1"},
            "notification_type": "EMAIL",
            "channel_id": channel.id,
            "recipients": ["1"],
            "title": "Hello",
            "body": "Body",
        }
    )
    assert output["delivery"]["retryable"] is False

    email = Channel.objects.create(name="邮件", channel_type="email", description="mail", team=[1], config={})
    with pytest.raises(ValueError):
        handler.execute(
            {
                "__bklite_context": {"organization_id": 1, "execution_id": "ex-2"},
                "notification_type": "EMAIL",
                "channel_id": email.id,
                "recipients": ["1"],
                "title": "Hello",
                "body": "Body",
            }
        )
