import pytest
from rest_framework import serializers

from apps.operation_analysis.models.datasource_models import DataConnection, DataSourceAPIModel
from apps.operation_analysis.serializers.data_connection_serializers import (
    DataConnectionSerializer,
    validate_rest_headers,
    validate_datasource_connection_binding,
)
from apps.operation_analysis.services.data_connection.config_crypto import (
    decrypt_connection_config,
    encrypt_connection_config,
)
from apps.operation_analysis.services.data_connection.groups import is_groups_subset
from apps.operation_analysis.services.data_connection.resolver import (
    ConnectionResolveError,
    resolve_datasource_connection,
)
from apps.operation_analysis.views.data_connection_view import (
    REFERENCE_SUMMARY_LIMIT,
    extract_inline_connection,
    visible_connection_references,
)

pytestmark = [pytest.mark.django_db]


def test_groups_subset_invariant():
    assert is_groups_subset([1], [1, 2]) is True
    assert is_groups_subset([1, 2], [1]) is False
    assert is_groups_subset([], [1]) is False


@pytest.mark.parametrize(
    "header_name",
    ["Host", "content-length", "Transfer-Encoding", "Connection", "Proxy-Authorization"],
)
def test_rest_connection_rejects_controlled_headers(header_name):
    with pytest.raises(serializers.ValidationError):
        validate_rest_headers({header_name: "controlled"})


def test_data_connection_serializer_uses_description_field():
    model_fields = {field.name for field in DataConnection._meta.fields}

    assert "description" in model_fields
    assert "desc" not in model_fields
    assert "description" in DataConnectionSerializer.Meta.fields
    assert "desc" not in DataConnectionSerializer.Meta.fields


def test_encrypt_and_decrypt_connection_config_roundtrip():
    encrypted = encrypt_connection_config(
        {
            "host": "db.example.com",
            "port": 3306,
            "database": "ops",
            "username": "reader",
            "password": "plain-secret",
            "headers": {"Authorization": "Bearer token"},
        }
    )
    assert encrypted["password"].startswith("enc$")
    assert encrypted["headers"]["Authorization"].startswith("enc$")
    assert encrypted["host"] == "db.example.com"
    decrypted = decrypt_connection_config(encrypted)
    assert decrypted["password"] == "plain-secret"
    assert decrypted["headers"]["Authorization"] == "Bearer token"


def test_resolve_mysql_connection_with_database_override():
    connection = DataConnection.objects.create(
        name="mysql-main",
        connection_type=DataConnection.TYPE_MYSQL,
        groups=[1],
        config=encrypt_connection_config(
            {
                "host": "db.example.com",
                "port": 3306,
                "database": "default_db",
                "username": "reader",
                "password": "secret",
            }
        ),
    )
    datasource = DataSourceAPIModel.objects.create(
        name="orders",
        source_type=DataSourceAPIModel.SOURCE_TYPE_MYSQL,
        groups=[1],
        connection=connection,
        connection_overrides={"database": "orders_db"},
        query_config={"sql": "SELECT 1"},
    )
    resolved = resolve_datasource_connection(datasource, current_team=1)
    assert resolved["host"] == "db.example.com"
    assert resolved["database"] == "orders_db"
    assert resolved["password"] == "secret"


def test_resolve_inactive_connection_fails():
    connection = DataConnection.objects.create(
        name="mysql-off",
        connection_type=DataConnection.TYPE_MYSQL,
        groups=[1],
        is_active=False,
        config=encrypt_connection_config(
            {
                "host": "db.example.com",
                "port": 3306,
                "database": "default_db",
                "username": "reader",
                "password": "secret",
            }
        ),
    )
    datasource = DataSourceAPIModel.objects.create(
        name="orders-off",
        source_type=DataSourceAPIModel.SOURCE_TYPE_MYSQL,
        groups=[1],
        connection=connection,
    )
    with pytest.raises(ConnectionResolveError) as exc:
        resolve_datasource_connection(datasource, current_team=1)
    assert exc.value.code == "connection_inactive"


def test_delete_referenced_connection_is_protected():
    connection = DataConnection.objects.create(
        name="pg-shared",
        connection_type=DataConnection.TYPE_POSTGRESQL,
        groups=[1],
        config=encrypt_connection_config(
            {
                "host": "pg.example.com",
                "port": 5432,
                "database": "ops",
                "username": "reader",
                "password": "secret",
            }
        ),
    )
    DataSourceAPIModel.objects.create(
        name="pg-ds",
        source_type=DataSourceAPIModel.SOURCE_TYPE_POSTGRESQL,
        groups=[1],
        connection=connection,
        connection_overrides={"database": "analytics"},
        query_config={"sql": "SELECT 1"},
        chart_type=["table"],
        params=[],
    )
    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        connection.delete()


def test_datasource_groups_must_be_subset_of_connection():
    connection = DataConnection.objects.create(
        name="mysql-a",
        connection_type=DataConnection.TYPE_MYSQL,
        groups=[1],
        config=encrypt_connection_config(
            {
                "host": "db.example.com",
                "port": 3306,
                "database": "ops",
                "username": "reader",
                "password": "secret",
            }
        ),
    )
    with pytest.raises(serializers.ValidationError):
        validate_datasource_connection_binding(
            {
                "source_type": DataSourceAPIModel.SOURCE_TYPE_MYSQL,
                "groups": [1, 2],
                "connection": connection,
                "connection_overrides": {},
                "connection_config": {},
            }
        )


def test_resolve_rest_rejects_path_traversal():
    connection = DataConnection.objects.create(
        name="rest-base",
        connection_type=DataConnection.TYPE_REST_API,
        groups=[1],
        config=encrypt_connection_config(
            {
                "base_url": "https://api.example.com/v1/",
                "headers": {"Authorization": "Bearer token"},
            }
        ),
    )
    datasource = DataSourceAPIModel.objects.create(
        name="rest-ds",
        source_type=DataSourceAPIModel.SOURCE_TYPE_REST_API,
        groups=[1],
        connection=connection,
        connection_overrides={"path": "../admin"},
        chart_type=["table"],
        params=[],
    )
    with pytest.raises(ConnectionResolveError) as exc:
        resolve_datasource_connection(datasource, current_team=1)
    assert exc.value.code == "rest_path_invalid"


def test_resolve_rest_joins_safe_relative_path():
    connection = DataConnection.objects.create(
        name="rest-safe",
        connection_type=DataConnection.TYPE_REST_API,
        groups=[1],
        config=encrypt_connection_config(
            {
                "base_url": "https://api.example.com/v1/",
                "headers": {},
            }
        ),
    )
    datasource = DataSourceAPIModel.objects.create(
        name="rest-safe-ds",
        source_type=DataSourceAPIModel.SOURCE_TYPE_REST_API,
        groups=[1],
        connection=connection,
        connection_overrides={"path": "orders", "method": "GET"},
        chart_type=["table"],
        params=[],
    )
    resolved = resolve_datasource_connection(datasource, current_team=1)
    assert resolved["url"] == "https://api.example.com/v1/orders"
    assert resolved["method"] == "GET"


def test_extract_inline_connection():
    datasource = DataSourceAPIModel.objects.create(
        name="inline-mysql",
        source_type=DataSourceAPIModel.SOURCE_TYPE_MYSQL,
        groups=[1],
        connection_config={
            "host": "db.example.com",
            "port": 3306,
            "database": "ops",
            "username": "reader",
            "password": "secret",
        },
        query_config={"sql": "SELECT 1"},
        chart_type=["table"],
        params=[],
    )
    connection = extract_inline_connection(datasource, name="extracted-mysql")
    datasource.refresh_from_db()
    assert datasource.connection_id == connection.id
    assert connection.name == "extracted-mysql"
    assert datasource.connection_config == {}


def test_extract_inline_connection_uses_connection_config_override():
    datasource = DataSourceAPIModel.objects.create(
        name="inline-override",
        source_type=DataSourceAPIModel.SOURCE_TYPE_MYSQL,
        groups=[1],
        connection_config={
            "host": "old.example.com",
            "port": 3306,
            "database": "ops",
            "username": "reader",
            "password": "secret",
        },
    )

    connection = extract_inline_connection(
        datasource,
        name="overridden",
        connection_config={
            "host": "new.example.com",
            "port": 3307,
            "database": "ops2",
            "username": "reader2",
            "password": "******",
        },
    )
    datasource.refresh_from_db()

    assert connection.name == "overridden"
    assert decrypt_connection_config(connection.config)["host"] == "new.example.com"
    assert decrypt_connection_config(connection.config)["password"] == "secret"
    assert datasource.connection_id == connection.id


def test_extract_inline_connection_always_inherits_datasource_groups():
    datasource = DataSourceAPIModel.objects.create(
        name="inline-groups",
        source_type=DataSourceAPIModel.SOURCE_TYPE_MYSQL,
        groups=[1, 2],
        connection_config={
            "host": "db.example.com",
            "port": 3306,
            "database": "ops",
            "username": "reader",
            "password": "secret",
        },
    )

    connection = extract_inline_connection(datasource, name="group-safe")

    assert connection.groups == [1, 2]
    assert decrypt_connection_config(connection.config)["password"] == "secret"


def test_connection_references_are_team_scoped_and_bounded():
    connection = DataConnection.objects.create(
        name="shared-rest",
        connection_type=DataConnection.TYPE_REST_API,
        groups=[1, 2],
        config=encrypt_connection_config({"base_url": "https://example.com", "headers": {}}),
    )
    DataSourceAPIModel.objects.bulk_create(
        [
            DataSourceAPIModel(
                name=f"team-1-{index}",
                source_type=DataSourceAPIModel.SOURCE_TYPE_REST_API,
                groups=[1],
                connection=connection,
            )
            for index in range(REFERENCE_SUMMARY_LIMIT + 1)
        ]
        + [
            DataSourceAPIModel(
                name="team-2-only",
                source_type=DataSourceAPIModel.SOURCE_TYPE_REST_API,
                groups=[2],
                connection=connection,
            )
        ]
    )

    references = list(visible_connection_references(connection, 1)[:REFERENCE_SUMMARY_LIMIT])

    assert len(references) == REFERENCE_SUMMARY_LIMIT
    assert all(reference.groups == [1] for reference in references)


def test_resolve_preview_connection_config_for_unsaved_shared_connection():
    from apps.operation_analysis.views.datasource_view import _resolve_preview_connection_config

    connection = DataConnection.objects.create(
        name="mysql-preview",
        connection_type=DataConnection.TYPE_MYSQL,
        groups=[1],
        config=encrypt_connection_config(
            {
                "host": "db.example.com",
                "port": 3306,
                "database": "default_db",
                "username": "reader",
                "password": "secret",
            }
        ),
    )
    resolved = _resolve_preview_connection_config(
        {
            "source_type": DataSourceAPIModel.SOURCE_TYPE_MYSQL,
            "connection": connection.id,
            "connection_overrides": {"database": "orders"},
            "groups": [1],
        },
        current_team=1,
        groups=[1],
    )
    assert resolved["host"] == "db.example.com"
    assert resolved["database"] == "orders"
    assert resolved["password"] == "secret"
