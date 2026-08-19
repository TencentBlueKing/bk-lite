from datetime import datetime, timedelta, timezone
from io import StringIO

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command

from apps.core.utils.crypto.password_crypto import PasswordCrypto
from apps.operation_analysis.common.get_nats_source_data import GetNatsData
from apps.operation_analysis.management.commands import init_default_namespace
from apps.operation_analysis.models import datasource_models
from apps.operation_analysis.models.datasource_models import NameSpace, NamespacePasswordDecryptionError
from apps.operation_analysis.serializers.datasource_serializers import NameSpaceModelSerializer

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fixed_namespace_secret_key(monkeypatch):
    monkeypatch.setattr(datasource_models, "SECRET_KEY", "current-key")


def _namespace(**overrides):
    values = {
        "name": "custom",
        "namespace": "custom_namespace",
        "account": "nats-user",
        "password": "",
        "domain": "nats.example.com",
        "enable_tls": False,
    }
    values.update(overrides)
    return NameSpace(**values)


def test_decrypt_password_returns_plaintext_for_current_key():
    namespace = _namespace()
    namespace.set_password("plain-secret")

    assert namespace.decrypt_password == "plain-secret"


@pytest.mark.parametrize("blank_key", ["", " \t"])
def test_new_password_write_rejects_blank_secret_key(monkeypatch, blank_key):
    monkeypatch.setattr(datasource_models, "SECRET_KEY", blank_key)
    monkeypatch.delenv("OPERATION_ANALYSIS_ALLOW_INSECURE_CREDENTIAL_WRITES", raising=False)

    with pytest.raises(ImproperlyConfigured, match="SECRET_KEY 未配置"):
        _namespace().set_password("plain-secret")


def test_blank_key_legacy_ciphertext_remains_readable(monkeypatch):
    monkeypatch.setattr(datasource_models, "SECRET_KEY", "")
    stored_value = PasswordCrypto("").encrypt("plain-secret")

    assert _namespace(password=stored_value).decrypt_password == "plain-secret"


def test_explicit_legacy_write_switch_is_reversible(monkeypatch, caplog):
    monkeypatch.setattr(datasource_models, "SECRET_KEY", "")
    monkeypatch.setenv("OPERATION_ANALYSIS_ALLOW_INSECURE_CREDENTIAL_WRITES", "true")
    deadline = datetime.now(timezone.utc) + timedelta(minutes=5)
    monkeypatch.setenv("OPERATION_ANALYSIS_INSECURE_CREDENTIAL_WRITES_UNTIL", deadline.isoformat())
    namespace = _namespace()

    namespace.set_password("plain-secret")

    assert namespace.decrypt_password == "plain-secret"
    assert "临时兼容开关" in caplog.text


@pytest.mark.parametrize("switch_value", ["", "0", "false", "invalid"])
def test_legacy_write_switch_rejects_non_true_values(monkeypatch, switch_value):
    monkeypatch.setattr(datasource_models, "SECRET_KEY", "")
    monkeypatch.setenv("OPERATION_ANALYSIS_ALLOW_INSECURE_CREDENTIAL_WRITES", switch_value)

    with pytest.raises(ImproperlyConfigured, match="SECRET_KEY 未配置"):
        _namespace().set_password("plain-secret")


@pytest.mark.parametrize("deadline", ["", "invalid", "2026-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"])
def test_legacy_write_switch_rejects_missing_invalid_or_unbounded_deadline(monkeypatch, deadline):
    monkeypatch.setattr(datasource_models, "SECRET_KEY", "")
    monkeypatch.setenv("OPERATION_ANALYSIS_ALLOW_INSECURE_CREDENTIAL_WRITES", "true")
    monkeypatch.setenv("OPERATION_ANALYSIS_INSECURE_CREDENTIAL_WRITES_UNTIL", deadline)

    with pytest.raises(ImproperlyConfigured, match="SECRET_KEY 未配置"):
        _namespace().set_password("plain-secret")


def test_decrypt_password_rejects_unreadable_value_without_exposing_credentials():
    stored_value = PasswordCrypto("old-key").encrypt("plain-secret")
    namespace = _namespace(password=stored_value)

    with pytest.raises(NamespacePasswordDecryptionError, match="命名空间密码解密失败") as error:
        _ = namespace.decrypt_password

    assert stored_value not in str(error.value)
    assert "plain-secret" not in str(error.value)


def test_unreadable_password_stops_before_nats_rpc_call():
    calls = []

    class FakeClient:
        DEFAULT_NATS = True

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_customization_nast_data(self, **kwargs):
            calls.append(kwargs)
            return {"result": True}

    class UnreadableNamespace:
        id = 1
        name = "custom"
        namespace = "custom_namespace"
        account = "nats-user"

        @property
        def decrypt_password(self):
            raise ValueError("命名空间密码解密失败，请重新录入密码")

    class TestGetNatsData(GetNatsData):
        @property
        def default_nats_client(self):
            return FakeClient

    obj = TestGetNatsData.__new__(TestGetNatsData)
    obj.path = "query"
    obj.params = {}
    obj.namespace = "custom"
    obj.namespace_list = [UnreadableNamespace()]
    obj.namespace_server_map = {1: "nats://nats.example.com:4222"}

    with pytest.raises(ValueError, match="命名空间密码解密失败"):
        obj.get_data()

    assert calls == []


@pytest.mark.django_db
def test_partial_update_without_password_preserves_unreadable_stored_value():
    namespace = NameSpace.objects.create(
        name="legacy",
        namespace="custom_namespace",
        account="nats-user",
        password="initial-password",
        domain="old.example.com",
    )
    stored_value = PasswordCrypto("old-key").encrypt("plain-secret")
    NameSpace.objects.filter(pk=namespace.pk).update(password=stored_value)
    namespace.refresh_from_db()

    serializer = NameSpaceModelSerializer(
        namespace,
        data={"domain": "new.example.com"},
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    namespace.refresh_from_db()

    assert namespace.domain == "new.example.com"
    assert namespace.password == stored_value


@pytest.mark.django_db
def test_partial_update_with_password_encrypts_new_value():
    namespace = NameSpace.objects.create(
        name="editable",
        namespace="custom_namespace",
        account="nats-user",
        password="initial-password",
        domain="nats.example.com",
    )

    serializer = NameSpaceModelSerializer(
        namespace,
        data={"password": "rotated-password"},
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    namespace.refresh_from_db()

    assert namespace.password != "rotated-password"
    assert namespace.decrypt_password == "rotated-password"


@pytest.mark.django_db
def test_partial_update_with_empty_password_still_clears_password(monkeypatch):
    namespace = NameSpace.objects.create(
        name="clearable",
        namespace="custom_namespace",
        account="nats-user",
        password="initial-password",
        domain="nats.example.com",
    )
    monkeypatch.setattr(datasource_models, "SECRET_KEY", "")

    serializer = NameSpaceModelSerializer(namespace, data={"password": ""}, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    namespace.refresh_from_db()

    assert namespace.password == ""


@pytest.mark.django_db
def test_create_still_encrypts_password():
    serializer = NameSpaceModelSerializer(
        data={
            "name": "created",
            "namespace": "custom_namespace",
            "account": "nats-user",
            "password": "plain-secret",
            "domain": "nats.example.com",
        }
    )
    serializer.is_valid(raise_exception=True)
    namespace = serializer.save()

    assert namespace.password != "plain-secret"
    assert namespace.decrypt_password == "plain-secret"


@pytest.mark.django_db
def test_default_namespace_init_survives_unreadable_password_and_recovers_after_rerecord(settings, monkeypatch):
    settings.NATS_SERVERS = "nats://admin:current-password@nats.example.com:4222"
    namespace = NameSpace.objects.create(name="默认命名空间", account="admin", password="initial-password", domain="nats.example.com:4222")
    stored_value = PasswordCrypto("old-key").encrypt("plain-secret")
    NameSpace.objects.filter(pk=namespace.pk).update(password=stored_value)
    logged_errors = []
    monkeypatch.setattr(init_default_namespace.logger, "error", lambda *args, **kwargs: logged_errors.append((args, kwargs)))

    failed_output = StringIO()
    call_command("init_default_namespace", stdout=failed_output)
    assert "命名空间密码解密失败，请重新录入密码" in failed_output.getvalue()
    assert stored_value not in failed_output.getvalue()
    assert "plain-secret" not in failed_output.getvalue()
    assert isinstance(logged_errors[0][0][1], NamespacePasswordDecryptionError)
    assert str(logged_errors[0][0][1]) == "命名空间密码解密失败，请重新录入密码"
    assert logged_errors[0][1]["exc_info"] is True

    namespace.refresh_from_db()
    serializer = NameSpaceModelSerializer(namespace, data={"password": "current-password"}, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()

    recovered_output = StringIO()
    call_command("init_default_namespace", stdout=recovered_output)
    assert "默认命名空间配置未变化" in recovered_output.getvalue()


@pytest.mark.django_db
def test_default_namespace_init_with_blank_key_logs_and_returns(settings, monkeypatch):
    settings.NATS_SERVERS = "nats://admin:current-password@nats.example.com:4222"
    monkeypatch.setattr(datasource_models, "SECRET_KEY", "")
    logged_errors = []
    monkeypatch.setattr(init_default_namespace.logger, "error", lambda *args, **kwargs: logged_errors.append((args, kwargs)))

    output = StringIO()
    call_command("init_default_namespace", stdout=output)

    assert "SECRET_KEY 未配置" in output.getvalue()
    assert not NameSpace.objects.filter(name="默认命名空间").exists()
    assert isinstance(logged_errors[0][0][1], ImproperlyConfigured)
    assert logged_errors[0][1]["exc_info"] is True
