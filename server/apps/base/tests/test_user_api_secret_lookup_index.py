"""API 密钥查找必须走 api_secret 普通索引，且认证语义保持不变。"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.base.models import UserAPISecret
from apps.base.tests.factories import UserAPISecretFactory


def _api_secret_select_count(captured) -> int:
    table = UserAPISecret._meta.db_table.lower()
    count = 0
    for query in captured.captured_queries:
        sql = query["sql"].lower().replace('"', "").replace("`", "")
        if "select" in sql and table in sql:
            count += 1
    return count


def _table_indexes_include_api_secret() -> bool:
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, UserAPISecret._meta.db_table)
    for spec in constraints.values():
        columns = list(spec.get("columns") or [])
        if "api_secret" not in columns:
            continue
        if spec.get("index") or spec.get("unique"):
            return True
    return False


@pytest.mark.unit
@pytest.mark.django_db
def test_api_secret_field_has_db_index():
    field = UserAPISecret._meta.get_field("api_secret")
    assert field.db_index is True
    assert field.unique is False


@pytest.mark.unit
@pytest.mark.django_db
def test_api_secret_table_has_lookup_index():
    assert _table_indexes_include_api_secret()


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize("row_count", [1, 10, 100])
def test_hashed_lookup_query_count_does_not_grow_with_secret_count(row_count):
    target_raw = UserAPISecret.generate_api_secret()
    UserAPISecretFactory(
        username="lookup-target",
        domain="index.test",
        team=0,
        api_secret=UserAPISecret.hash_api_secret(target_raw),
    )
    extras = [
        UserAPISecret(
            username=f"lookup-extra-{index}",
            domain="index.test",
            team=0,
            api_secret=UserAPISecret.hash_api_secret(UserAPISecret.generate_api_secret()),
        )
        for index in range(row_count - 1)
    ]
    if extras:
        UserAPISecret.objects.bulk_create(extras)

    with CaptureQueriesContext(connection) as captured:
        found = UserAPISecret.find_by_api_secret(target_raw)

    assert found is not None
    assert found.username == "lookup-target"
    assert _api_secret_select_count(captured) == 1


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize("row_count", [1, 10, 100])
def test_unknown_token_uses_hashed_then_plaintext_lookup(row_count):
    UserAPISecret.objects.bulk_create(
        [
            UserAPISecret(
                username=f"unknown-extra-{index}",
                domain="index.test",
                team=1,
                api_secret=UserAPISecret.hash_api_secret(UserAPISecret.generate_api_secret()),
            )
            for index in range(row_count)
        ]
    )
    unknown = UserAPISecret.generate_api_secret()

    with CaptureQueriesContext(connection) as captured:
        found = UserAPISecret.find_by_api_secret(unknown)

    assert found is None
    assert _api_secret_select_count(captured) == 2


@pytest.mark.unit
def test_empty_and_hashed_inputs_are_rejected():
    assert UserAPISecret.find_by_api_secret("") is None
    hashed = UserAPISecret.hash_api_secret(UserAPISecret.generate_api_secret())
    assert UserAPISecret.find_by_api_secret(hashed) is None


@pytest.mark.unit
@pytest.mark.django_db
def test_plaintext_fallback_still_matches_unhashed_row():
    raw_secret = UserAPISecret.generate_api_secret()
    stored = UserAPISecretFactory(username="legacy-plain", api_secret=raw_secret)

    assert UserAPISecret.find_by_api_secret(raw_secret) == stored
