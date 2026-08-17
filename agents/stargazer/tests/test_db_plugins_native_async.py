# -*- coding: utf-8 -*-
"""MySQL / PostgreSQL / Oracle / MSSQL 原生异步插件单测。"""

from __future__ import annotations

import asyncio
import time

import pytest

from core.collection.contracts import AccessProbeStatus
from plugins.inputs.mysql.mysql_info import MysqlInfo
from plugins.inputs.postgresql.postgresql_info import PostgresqlInfo
from plugins.inputs.oracle.oracle_info import OracleInfo
from plugins.inputs.mssql.mssql_info import MSSQLInfo


async def _heartbeat_during(awaitable, minimum_ticks: int = 5):
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        result = await awaitable
    finally:
        heartbeat_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await heartbeat_task
    assert ticks >= minimum_ticks, "event_loop_stalled"
    return result


# ---------------------------------------------------------------------------
# MySQL
# ---------------------------------------------------------------------------
class _AsyncCursor:
    def __init__(self, rows_by_query: dict):
        self.rows_by_query = rows_by_query
        self._last = []

    async def execute(self, query):
        await asyncio.sleep(0.05)
        self._last = list(self.rows_by_query.get(query, []))

    async def fetchall(self):
        return self._last

    async def fetchone(self):
        return self._last[0] if self._last else None

    @property
    def description(self):
        if not self._last:
            return []
        return [(key,) for key in self._last[0].keys()]

    async def close(self):
        return None


class _AsyncMysqlConn:
    def __init__(self, rows_by_query: dict):
        self.rows_by_query = rows_by_query
        self.closed = False

    async def cursor(self, *_args, **_kwargs):
        return _AsyncCursor(self.rows_by_query)

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_mysql_probe_native_async_does_not_stall(monkeypatch):
    rows = {"SHOW GLOBAL VARIABLES LIKE 'version'": [{"Variable_name": "version", "Value": "8.0.36"}]}

    async def connect(**_kwargs):
        await asyncio.sleep(0.05)
        return _AsyncMysqlConn(rows)

    monkeypatch.setattr(
        "plugins.inputs.mysql.mysql_info.aiomysql.connect", connect
    )
    plugin = MysqlInfo(
        {"host": "10.0.0.8", "port": 3306, "user": "collector", "password": "secret"}
    )
    result = await _heartbeat_during(plugin.probe())
    assert result.status == AccessProbeStatus.READY
    assert result.evidence == {"server_version": "8.0.36"}


@pytest.mark.asyncio
async def test_mysql_probe_auth_failure(monkeypatch):
    from pymysql.err import OperationalError

    async def rejected(**_kwargs):
        raise OperationalError(1045, "Access denied for password secret-do-not-return")

    monkeypatch.setattr(
        "plugins.inputs.mysql.mysql_info.aiomysql.connect", rejected
    )
    result = await MysqlInfo(
        {"host": "10.0.0.8", "user": "collector", "password": "secret-do-not-return"}
    ).probe()
    assert result.status == AccessProbeStatus.AUTH_FAILED
    assert result.error_code == "authentication_failed"
    assert "secret-do-not-return" not in result.detail


@pytest.mark.asyncio
async def test_mysql_list_all_resources_native_async(monkeypatch):
    rows = {
        'SELECT table_schema AS "name", '
        'SUM(data_length + index_length) AS "size" '
        'FROM information_schema.TABLES GROUP BY table_schema': [
            {"name": "app", "size": 10}
        ],
        "SHOW GLOBAL VARIABLES": [
            {"Variable_name": "version", "Value": "8.0.36"},
            {"Variable_name": "log_bin", "Value": "ON"},
            {"Variable_name": "sync_binlog", "Value": "1"},
            {"Variable_name": "max_connections", "Value": "151"},
            {"Variable_name": "max_allowed_packet", "Value": "67108864"},
            {"Variable_name": "basedir", "Value": "/usr"},
            {"Variable_name": "datadir", "Value": "/var/lib/mysql"},
            {"Variable_name": "socket", "Value": "/tmp/mysql.sock"},
            {"Variable_name": "bind_address", "Value": "0.0.0.0"},
            {"Variable_name": "slow_query_log", "Value": "OFF"},
            {"Variable_name": "slow_query_log_file", "Value": ""},
            {"Variable_name": "log_error", "Value": "/var/log/mysql.err"},
            {"Variable_name": "wait_timeout", "Value": "28800"},
            {"Variable_name": "server_uuid", "Value": "uuid-1"},
        ],
        "SHOW MASTER STATUS": [],
        "SHOW BINARY LOG STATUS": [],
        "SHOW SLAVE STATUS": [],
        "SHOW REPLICA STATUS": [],
        "SHOW SLAVE HOSTS": [],
        "SHOW REPLICA HOSTS": [],
    }

    async def connect(**_kwargs):
        return _AsyncMysqlConn(rows)

    monkeypatch.setattr(
        "plugins.inputs.mysql.mysql_info.aiomysql.connect", connect
    )
    result = await MysqlInfo(
        {"host": "10.0.0.8", "port": 3306, "user": "u", "password": "p"}
    ).list_all_resources()
    assert result["success"] is True
    row = result["result"]["mysql"][0]
    assert row["version"] == "8.0.36"
    assert row["ip_addr"] == "10.0.0.8"
    assert row["role"] == "standalone"


# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
class _PgCursor:
    def __init__(self, rows_by_query):
        self.rows_by_query = rows_by_query
        self._last = []

    async def execute(self, query):
        await asyncio.sleep(0.05)
        self._last = list(self.rows_by_query.get(query, []))

    async def fetchall(self):
        return self._last

    async def close(self):
        return None


class _PgConn:
    def __init__(self, rows_by_query):
        self.rows_by_query = rows_by_query

    def cursor(self):
        return _PgCursor(self.rows_by_query)

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_postgresql_probe_native_async_does_not_stall(monkeypatch):
    rows = {"SHOW server_version": [{"server_version": "16.2"}]}

    async def connect(**_kwargs):
        await asyncio.sleep(0.05)
        return _PgConn(rows)

    monkeypatch.setattr(
        "plugins.inputs.postgresql.postgresql_info.psycopg.AsyncConnection.connect",
        connect,
    )
    result = await _heartbeat_during(
        PostgresqlInfo(
            {"host": "10.0.0.9", "user": "collector", "password": "secret"}
        ).probe()
    )
    assert result.status == AccessProbeStatus.READY
    assert result.evidence == {"server_version": "16.2"}


@pytest.mark.asyncio
async def test_postgresql_list_all_resources_native_async(monkeypatch):
    rows = {
        "SHOW server_version": [{"server_version": "16.2"}],
        "SHOW config_file": [{"config_file": "/etc/postgresql/postgresql.conf"}],
        "SHOW data_directory": [{"data_directory": "/var/lib/postgresql"}],
        "SHOW max_connections": [{"max_connections": "100"}],
        "SHOW shared_buffers": [{"shared_buffers": "128MB"}],
        "SHOW log_directory": [{"log_directory": "log"}],
    }

    async def connect(**_kwargs):
        return _PgConn(rows)

    monkeypatch.setattr(
        "plugins.inputs.postgresql.postgresql_info.psycopg.AsyncConnection.connect",
        connect,
    )
    result = await PostgresqlInfo(
        {"host": "10.0.0.9", "port": 5432, "user": "u", "password": "p"}
    ).list_all_resources()
    assert result["success"] is True
    row = result["result"]["postgresql"][0]
    assert row["version"] == "16.2"
    assert row["cache_memory_mb"] == 128
    assert row["log_path"] == "/var/lib/postgresql/log"


# ---------------------------------------------------------------------------
# Oracle
# ---------------------------------------------------------------------------
class _OracleCursor:
    def __init__(self, rows):
        self.rows = rows
        self.description = []
        self._row = None

    async def execute(self, query):
        await asyncio.sleep(0.02)
        self._row = self.rows.get(query)
        self.description = [(k,) for k in (self._row or {}).keys()]

    async def fetchone(self):
        if not self._row:
            return None
        return tuple(self._row.values())

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class _OracleConn:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return _OracleCursor(self.rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


@pytest.mark.asyncio
async def test_oracle_list_all_resources_native_async(monkeypatch):
    rows = {
        OracleInfo.SQL_QUERIES["version"]: {"BANNER": "Oracle Database 19c"},
        OracleInfo.SQL_QUERIES["max_mem"]: {"TOTAL_MEMORY": 1024},
        OracleInfo.SQL_QUERIES["max_conn"]: {"VALUE": 300},
        OracleInfo.SQL_QUERIES["db_name"]: {"NAME": "ORCL"},
        OracleInfo.SQL_QUERIES["database_role"]: {"DATABASE_ROLE": "PRIMARY"},
        OracleInfo.SQL_QUERIES["sid"]: {"SID": "orcl"},
    }

    async def connect_async(**_kwargs):
        await asyncio.sleep(0.05)
        return _OracleConn(rows)

    monkeypatch.setattr(
        "plugins.inputs.oracle.oracle_info.oracledb.connect_async", connect_async
    )
    result = await _heartbeat_during(
        OracleInfo(
            {
                "host": "10.0.0.10",
                "port": 1521,
                "user": "system",
                "password": "secret",
                "service_name": "orclpdb",
            }
        ).list_all_resources()
    )
    assert result["success"] is True
    row = result["result"]["oracle"][0]
    assert row["version"] == "Oracle Database 19c"
    assert row["db_name"] == "ORCL"
    assert row["sid"] == "orcl"


# ---------------------------------------------------------------------------
# MSSQL
# ---------------------------------------------------------------------------
class _MssqlCursor:
    def __init__(self, rows):
        self.rows = rows
        self.description = []
        self._row = None

    async def execute(self, query):
        await asyncio.sleep(0.02)
        self._row = self.rows.get(query)
        self.description = [(k,) for k in (self._row or {}).keys()]

    async def fetchone(self):
        if not self._row:
            return None
        return tuple(self._row.values())

    async def close(self):
        return None


class _MssqlConn:
    def __init__(self, rows):
        self.rows = rows

    async def cursor(self):
        return _MssqlCursor(self.rows)

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_mssql_list_all_resources_native_async(monkeypatch):
    rows = {
        MSSQLInfo.SQL_QUERIES["version"]: {"version": "15.0.2000.5"},
        MSSQLInfo.SQL_QUERIES["max_conn"]: {"max_conn": 0},
        MSSQLInfo.SQL_QUERIES["max_mem"]: {"max_mem_mb": 2048},
        MSSQLInfo.SQL_QUERIES["order_rule"]: {"order_rule": "Chinese_PRC_CI_AS"},
        MSSQLInfo.SQL_QUERIES["fill_factor"]: {"fill_factor": 0},
        MSSQLInfo.SQL_QUERIES["boot_account"]: {"boot_account": "NT SERVICE\\MSSQLSERVER"},
    }

    async def connect(**_kwargs):
        await asyncio.sleep(0.05)
        return _MssqlConn(rows)

    monkeypatch.setattr(
        "plugins.inputs.mssql.mssql_info.aioodbc.connect", connect
    )
    result = await _heartbeat_during(
        MSSQLInfo(
            {
                "host": "10.0.0.11",
                "port": 1433,
                "user": "sa",
                "password": "secret",
                "database": "master",
            }
        ).list_all_resources()
    )
    assert result["success"] is True
    row = result["result"]["mssql"][0]
    assert row["version"] == "15.0.2000.5"
    assert row["max_mem"] == "2048"
    assert "secret" not in str(result)


@pytest.mark.asyncio
async def test_db_plugins_do_not_use_to_thread_wrappers():
    """原生异步改造后，公开入口不应再依赖 to_thread 包装。"""
    import inspect
    from plugins.inputs.mysql import mysql_info as mysql_mod
    from plugins.inputs.postgresql import postgresql_info as pg_mod
    from plugins.inputs.oracle import oracle_info as oracle_mod
    from plugins.inputs.mssql import mssql_info as mssql_mod

    for mod in (mysql_mod, pg_mod, oracle_mod, mssql_mod):
        source = inspect.getsource(mod)
        assert "asyncio.to_thread" not in source
        assert "time.sleep" not in source
