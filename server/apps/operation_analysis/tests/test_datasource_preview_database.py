import pytest

from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.database import build_database_url, build_preview_sql, ensure_select_sql, normalize_db_rows


def test_ensure_select_sql_accepts_single_select():
    assert ensure_select_sql(" select id, name from users ") == "select id, name from users"


@pytest.mark.parametrize("sql", ["delete from users", "select 1; select 2", "update users set name='x'"])
def test_ensure_select_sql_rejects_dangerous_sql(sql):
    with pytest.raises(ConnectorError):
        ensure_select_sql(sql)


def test_build_preview_sql_from_mysql_table_name_quotes_identifier():
    assert build_preview_sql({"table": "orders"}, 100, "mysql") == "SELECT * FROM `orders` LIMIT 100"


def test_build_preview_sql_from_postgresql_table_name_quotes_identifier():
    assert build_preview_sql({"table": "orders"}, 100, "postgresql") == 'SELECT * FROM "orders" LIMIT 100'


def test_build_preview_sql_adds_limit_to_select():
    assert build_preview_sql({"sql": "select id from orders"}, 20) == "select id from orders LIMIT 20"


def test_build_database_url_for_mysql_uses_utf8mb4_charset():
    url = build_database_url(
        "mysql",
        {
            "host": "127.0.0.1",
            "port": 3306,
            "database": "ops",
            "username": "root",
            "password": "secret",
        },
    )

    assert url == "mysql+pymysql://root:secret@127.0.0.1:3306/ops?charset=utf8mb4"


def test_build_database_url_escapes_credentials():
    url = build_database_url(
        "postgresql",
        {
            "host": "127.0.0.1",
            "port": 5432,
            "database": "ops",
            "username": "ops user",
            "password": "pa:ss@word",
        },
    )

    assert url == "postgresql+psycopg2://ops+user:pa%3Ass%40word@127.0.0.1:5432/ops"


def test_normalize_db_rows_converts_row_mappings():
    rows = [{"id": 1, "name": "a"}]
    assert normalize_db_rows(rows) == [{"id": 1, "name": "a"}]
