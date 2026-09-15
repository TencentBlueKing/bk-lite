# -*- coding: utf-8 -*-
"""
Oracle Server Information Collector

A standalone script to gather information about Oracle servers.
"""
from typing import Any, Dict, List

import oracledb
from plugins.inputs.oracle.oracle_topology import (
    build_dsn_parts,
    classify_collect_scope,
    cluster_type,
    database_inst_name,
    filter_business_pdbs,
    instance_inst_name,
    parse_cdb_flag,
    pdb_inst_name,
)
from sanic.log import logger


class OracleInfo:
    """Class for collecting Oracle instance, database and PDB information."""

    SQL_QUERIES = {
        "con_name": "SELECT SYS_CONTEXT('USERENV','CON_NAME') AS CON_NAME FROM DUAL",
        "database": "SELECT name, db_unique_name, database_role, log_mode, open_mode FROM v$database",
        "cdb_flag": "SELECT cdb FROM v$database",
        "charset": "SELECT value FROM nls_database_parameters WHERE parameter='NLS_CHARACTERSET'",
        "version": "SELECT * FROM v$version WHERE rownum=1",
        "sga_max_size": "SELECT value FROM v$parameter WHERE name='sga_max_size'",
        "memory_target": "SELECT value FROM v$parameter WHERE name='memory_target'",
        "max_conn": "SELECT value FROM v$parameter WHERE name='sessions'",
        "instance": "SELECT instance_name AS SID, host_name, status, version FROM v$instance",
        "gv_instance": "SELECT instance_name AS SID, host_name, status, version, instance_number FROM gv$instance",
        "pdbs": "SELECT name, open_mode, restricted FROM v$pdbs",
    }

    def __init__(self, kwargs: Dict[str, Any]):
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 1521))
        self.user = kwargs.get("user")
        self.password = kwargs.get("password", "")
        self.service_name = str(kwargs.get("service_name") or "").strip()
        self.sid = str(kwargs.get("sid") or "").strip()
        self.timeout = 20
        self.info: Dict[str, Any] = {}
        self.cursor = None

    def _connect_kwargs(self) -> dict[str, Any]:
        parts = build_dsn_parts(host=self.host, port=self.port, service_name=self.service_name, sid=self.sid)
        dsn = oracledb.makedsn(**parts)
        return {
            "user": self.user,
            "password": self.password,
            "dsn": dsn,
            "tcp_connect_timeout": self.timeout,
        }

    async def _exec_sql(self, query: str) -> Dict[str, Any]:
        rows = await self._exec_sql_all(query)
        return rows[0] if rows else {}

    async def _exec_sql_all(self, query: str) -> List[Dict[str, Any]]:
        logger.debug("Executing SQL query: %s", query)
        await self.cursor.execute(query)
        cols = [col[0] for col in self.cursor.description]
        fetchall = getattr(self.cursor, "fetchall", None)
        if callable(fetchall):
            rows = await fetchall()
        else:
            row = await self.cursor.fetchone()
            rows = [row] if row else []
        result = []
        for row in rows or []:
            if row is None:
                continue
            item = dict(zip(cols, row))
            result.append({str(key).lower(): value for key, value in item.items()})
        return result

    async def _try_sql(self, query: str) -> Dict[str, Any]:
        try:
            return await self._exec_sql(query)
        except Exception as exc:  # noqa: BLE001 - 可选视图缺失不能阻断整次采集
            logger.debug("Optional SQL skipped: %s", type(exc).__name__)
            return {}

    async def _try_sql_all(self, query: str) -> List[Dict[str, Any]] | None:
        try:
            return await self._exec_sql_all(query)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Optional SQL list skipped: %s", type(exc).__name__)
            return None

    async def _collect(self) -> dict[str, list[dict[str, Any]]]:
        con_name = str((await self._try_sql(self.SQL_QUERIES["con_name"])).get("con_name") or "")
        database = await self._try_sql(self.SQL_QUERIES["database"])
        is_cdb = parse_cdb_flag((await self._try_sql(self.SQL_QUERIES["cdb_flag"])).get("cdb"))
        charset = str((await self._try_sql(self.SQL_QUERIES["charset"])).get("value") or "")
        version = str((await self._try_sql(self.SQL_QUERIES["version"])).get("banner") or "")
        sga_max = str((await self._try_sql(self.SQL_QUERIES["sga_max_size"])).get("value") or "")
        memory_target = str((await self._try_sql(self.SQL_QUERIES["memory_target"])).get("value") or "")
        max_conn = str((await self._try_sql(self.SQL_QUERIES["max_conn"])).get("value") or "")
        current_instance = await self._try_sql(self.SQL_QUERIES["instance"])
        gv_rows = await self._try_sql_all(self.SQL_QUERIES["gv_instance"])
        pdb_rows = await self._try_sql_all(self.SQL_QUERIES["pdbs"])

        db_name = str(database.get("name") or "")
        db_unique_name = str(database.get("db_unique_name") or "")
        db_key = database_inst_name(db_unique_name, db_name)
        sid = str(current_instance.get("sid") or "")
        scope = classify_collect_scope(
            con_name=con_name,
            is_cdb=is_cdb,
            pdbs_available=pdb_rows is not None,
        )
        if is_cdb is None:
            is_cdb = scope != "non_cdb"

        instances = gv_rows if gv_rows else ([current_instance] if current_instance else [])
        if not instances and sid:
            instances = [{"sid": sid, "host_name": "", "status": "", "version": version}]

        pdb_items = filter_business_pdbs(pdb_rows or [], scope=scope, current_pdb=con_name)

        oracle_row = {
            "inst_name": db_key or f"{self.host}-oracle-{self.port}",
            "ip_addr": self.host,
            "port": self.port,
            "sid": sid,
            "service_name": self.service_name,
            "db_name": db_name,
            "db_unique_name": db_unique_name or db_name,
            "version": version,
            "database_role": str(database.get("database_role") or ""),
            "open_mode": str(database.get("open_mode") or ""),
            "log_mode": str(database.get("log_mode") or ""),
            "nls_characterset": charset,
            "max_mem": sga_max or memory_target or "0",
            "max_conn": max_conn,
            "is_cdb": "true" if is_cdb else "false",
            "collect_scope": scope,
            "cluster_type": cluster_type(len(instances)),
            "instance_count": str(len(instances)),
            "pdb_count": str(len(pdb_items)),
        }

        instance_rows = []
        for item in instances:
            inst_sid = str(item.get("sid") or "")
            host_name = str(item.get("host_name") or "")
            ip_addr = self.host if _upper_sid(inst_sid) == _upper_sid(sid) else host_name
            instance_rows.append(
                {
                    "inst_name": instance_inst_name(db_key, inst_sid),
                    "db_unique_name": oracle_row["db_unique_name"],
                    "sid": inst_sid,
                    "host_name": host_name,
                    "ip_addr": ip_addr,
                    "port": self.port,
                    "status": str(item.get("status") or ""),
                    "version": str(item.get("version") or version),
                }
            )

        pdb_models = []
        for pdb in pdb_items:
            pdb_name = str(pdb.get("name") or "")
            pdb_models.append(
                {
                    "inst_name": pdb_inst_name(db_key, pdb_name),
                    "db_unique_name": oracle_row["db_unique_name"],
                    "pdb_name": pdb_name,
                    "open_mode": str(pdb.get("open_mode") or ""),
                    "restricted": str(pdb.get("restricted") or ""),
                    "service_name": pdb_name,
                }
            )

        self.info = oracle_row
        return {
            "oracle": [oracle_row],
            "oracle_instance": instance_rows,
            "oracle_pdb": pdb_models,
        }

    async def list_all_resources(self) -> dict[str, Any]:
        try:
            async with await oracledb.connect_async(**self._connect_kwargs()) as connection:
                async with connection.cursor() as cursor:
                    self.cursor = cursor
                    collected = await self._collect()
            result = {"result": collected, "success": True}
            logger.info("Data collection completed successfully.")
        except ValueError as exc:
            logger.error("Oracle connect config error: %s", type(exc).__name__)
            result = {"result": {"cmdb_collect_error": str(exc)}, "success": False}
        except oracledb.Error as exc:
            logger.error("Database error in OracleInfo: %s", type(exc).__name__)
            result = {"result": {"cmdb_collect_error": f"Database error: {exc}"}, "success": False}
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error in OracleInfo: %s", type(exc).__name__)
            result = {"result": {"cmdb_collect_error": f"Unexpected error: {exc}"}, "success": False}
        finally:
            self.cursor = None
        return result


def _upper_sid(value: str) -> str:
    return str(value or "").strip().upper()
