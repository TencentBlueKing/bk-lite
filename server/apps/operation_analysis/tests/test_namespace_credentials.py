import pytest

from apps.core.utils.crypto.password_crypto import PasswordCrypto
from apps.operation_analysis.common.get_nats_source_data import GetNatsData
from apps.operation_analysis.models import datasource_models
from apps.operation_analysis.models.datasource_models import NameSpace
from apps.operation_analysis.serializers.datasource_serializers import NameSpaceModelSerializer


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


def test_decrypt_password_rejects_unreadable_value_without_exposing_credentials():
    stored_value = PasswordCrypto("old-key").encrypt("plain-secret")
    namespace = _namespace(password=stored_value)

    with pytest.raises(ValueError, match="命名空间密码解密失败") as error:
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
