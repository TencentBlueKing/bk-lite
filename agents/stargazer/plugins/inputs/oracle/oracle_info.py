# -*- coding: utf-8 -*-
"""
Oracle Server Information Collector

A standalone script to gather information about Oracle servers.
"""
from typing import Any, Dict, List

import oracledb
from plugins.inputs.oracle.oracle_topology import (
    classify_collect_scope,
    cluster_type,
    database_inst_name,
    filter_business_pdbs,
    instance_inst_name,
    parse_cdb_flag,
    pdb_inst_name,
)
from sanic.log import logger

DEFAULT_SERVICE_NAME = "orclpdb"


class OracleInfo:
    """Class for collecting Oracle instance, database and PDB information."""

    SQL_QUERIES = {
        "version": "SELECT * FROM v$version WHERE rownum=1",
        "max_mem": "SELECT SUM(value) AS TOTAL_MEMORY FROM v$sga",
        "max_conn": "SELECT value FROM v$parameter WHERE name='sessions'",
        "db_name": "SELECT name FROM v$database",
        "database_role": "SELECT database_role FROM v$database",
        "sid": "SELECT INSTANCE_NAME AS SID FROM V$INSTANCE",
        "con_name": "SELECT SYS_CONTEXT('USERENV','CON_NAME') AS CON_NAME FROM DUAL",
        "database_extra": "SELECT db_unique_name, log_mode, open_mode FROM v$database",
        "cdb_flag": "SELECT cdb FROM v$database",
        "charset": "SELECT value FROM nls_database_parameters WHERE parameter='NLS_CHARACTERSET'",
        "instance": "SELECT instance_name AS SID, host_name, status, version FROM v$instance",
        "gv_instance": "SELECT instance_name AS SID, host_name, status, version, instance_number FROM gv$instance",
        "pdbs": "SELECT name, open_mode, restricted FROM v$pdbs",
    }

    def __init__(self, kwargs: Dict[str, Any]):
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 1521))
        self.user = kwargs.get("user")
        self.password = kwargs.get("password", "")
        self.sid = str(kwargs.get("sid") or "").strip()
        self.service_name = str(kwargs.get("service_name") or "").strip()
        if not self.service_name and not self.sid:
            self.service_name = DEFAULT_SERVICE_NAME
        self.timeout = 20  # 连接超时硬编码；表单 timeout 由框架作单对象预算
        self.info: Dict[str, Any] = {}
        self.connection = None
        self.cursor = None

    def _connect_kwargs(self) -> dict[str, Any]:
        if self.sid and not self.service_name:
            dsn = oracledb.makedsn(self.host, self.port, sid=self.sid)
        else:
            dsn = f"{self.host}:{self.port}/{self.service_name or DEFAULT_SERVICE_NAME}"
        return {
            "user": self.user,
            "password": self.password,
            "dsn": dsn,
            "tcp_connect_timeout": self.timeout,
        }

    async def _exec_sql(self, query: str) -> Dict[str, Any]:
        """Execute SQL query and return results as dict (first row only)."""
        try:
            logger.debug(f"Executing SQL query: {query}")
            await self.cursor.execute(query)
            cols = [col[0] for col in self.cursor.description]
            row = await self.cursor.fetchone()
            if row:
                return dict(zip(cols, row))
            return {}
        except oracledb.Error as e:
            logger.error(f"Error executing SQL '{query}': {str(e)}")
            raise RuntimeError(f"SQL execution error: {str(e)}")

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
        except Exception:  # noqa: BLE001 - 可选视图缺失不能阻断整次采集
            logger.debug("Optional SQL skipped")
            return {}

    async def _try_sql_all(self, query: str) -> List[Dict[str, Any]] | None:
        try:
            return await self._exec_sql_all(query)
        except Exception:  # noqa: BLE001
            logger.debug("Optional SQL list skipped")
            return None

    async def _collect(self) -> dict[str, list[dict[str, Any]]]:
        logger.info("Starting data collection from Oracle database.")
        try:
            self.info["version"] = _row_get(await self._exec_sql(self.SQL_QUERIES["version"]), "BANNER")
            self.info["max_mem"] = str(_row_get(await self._exec_sql(self.SQL_QUERIES["max_mem"]), "TOTAL_MEMORY", default=0))
            self.info["max_conn"] = str(_row_get(await self._exec_sql(self.SQL_QUERIES["max_conn"]), "VALUE", default=0))
            self.info["db_name"] = _row_get(await self._exec_sql(self.SQL_QUERIES["db_name"]), "NAME")
            self.info["database_role"] = _row_get(await self._exec_sql(self.SQL_QUERIES["database_role"]), "DATABASE_ROLE")
            self.info["sid"] = _row_get(await self._exec_sql(self.SQL_QUERIES["sid"]), "SID")
            self.info["ip_addr"] = self.host
            self.info["port"] = self.port
            self.info["service_name"] = self.service_name
            self.info["inst_name"] = f"{self.host}-oracle"
        except Exception as e:
            logger.error(f"Error during data collection: {str(e)}")
            raise

        extra = await self._try_sql(self.SQL_QUERIES["database_extra"])
        con_name = _row_get(await self._try_sql(self.SQL_QUERIES["con_name"]), "CON_NAME")
        is_cdb = parse_cdb_flag(_row_get(await self._try_sql(self.SQL_QUERIES["cdb_flag"]), "CDB"))
        charset = _row_get(await self._try_sql(self.SQL_QUERIES["charset"]), "VALUE")
        current_instance = await self._try_sql(self.SQL_QUERIES["instance"])
        gv_rows = await self._try_sql_all(self.SQL_QUERIES["gv_instance"])
        pdb_rows = await self._try_sql_all(self.SQL_QUERIES["pdbs"])

        db_unique_name = _row_get(extra, "DB_UNIQUE_NAME")
        db_key = database_inst_name(db_unique_name, self.info["db_name"])
        sid = self.info["sid"]
        scope = classify_collect_scope(con_name=con_name, is_cdb=is_cdb, pdbs_available=pdb_rows is not None)
        if is_cdb is None:
            is_cdb = scope != "non_cdb"

        instance_row = current_instance if isinstance(current_instance, dict) else {}
        instances = gv_rows if gv_rows else ([instance_row] if instance_row else [])
        if not instances and sid:
            instances = [{"sid": sid, "host_name": "", "status": "", "version": self.info["version"]}]

        pdb_items = filter_business_pdbs(pdb_rows or [], scope=scope, current_pdb=con_name)
        parent_inst_name = self.info["inst_name"]

        self.info.update(
            {
                "db_unique_name": db_unique_name or self.info["db_name"],
                "open_mode": _row_get(extra, "OPEN_MODE"),
                "log_mode": _row_get(extra, "LOG_MODE"),
                "nls_characterset": charset,
                "is_cdb": "true" if is_cdb else "false",
                "collect_scope": scope,
                "cluster_type": cluster_type(len(instances)),
                "instance_count": str(len(instances)),
                "pdb_count": str(len(pdb_items)),
            }
        )

        instance_rows = []
        for item in instances:
            inst_sid = str(item.get("sid") or item.get("SID") or "")
            host_name = str(item.get("host_name") or item.get("HOST_NAME") or "")
            ip_addr = self.host if _upper_sid(inst_sid) == _upper_sid(sid) else host_name
            instance_rows.append(
                {
                    "inst_name": instance_inst_name(db_key, inst_sid),
                    "db_unique_name": self.info["db_unique_name"],
                    "sid": inst_sid,
                    "host_name": host_name,
                    "ip_addr": ip_addr,
                    "port": self.port,
                    "status": str(item.get("status") or item.get("STATUS") or ""),
                    "version": str(item.get("version") or item.get("VERSION") or self.info["version"]),
                    "parent_ip": self.host,
                    "parent_inst_name": parent_inst_name,
                }
            )

        pdb_models = []
        for pdb in pdb_items:
            pdb_name = str(pdb.get("name") or pdb.get("NAME") or "")
            pdb_models.append(
                {
                    "inst_name": pdb_inst_name(db_key, pdb_name),
                    "db_unique_name": self.info["db_unique_name"],
                    "pdb_name": pdb_name,
                    "open_mode": str(pdb.get("open_mode") or pdb.get("OPEN_MODE") or ""),
                    "restricted": str(pdb.get("restricted") or pdb.get("RESTRICTED") or ""),
                    "service_name": pdb_name,
                    "parent_ip": self.host,
                    "parent_inst_name": parent_inst_name,
                }
            )

        return {
            "oracle": [self.info],
            "oracle_instance": instance_rows,
            "oracle_pdb": pdb_models,
        }

    async def list_all_resources(self) -> dict[str, Any]:
        """Public method to collect all info and format it for Prometheus."""
        try:
            async with await oracledb.connect_async(**self._connect_kwargs()) as connection:
                async with connection.cursor() as cursor:
                    self.cursor = cursor
                    try:
                        collected = await self._collect()
                    except Exception as e:
                        logger.error(f"Error during data collection: {str(e)}")
                        raise

            result = {"result": collected, "success": True}
            logger.info("Data collection completed successfully.")
        except oracledb.Error as e:
            logger.error(f"Database error in OracleInfo: {str(e)}")
            result = {"result": {"cmdb_collect_error": f"Database error: {str(e)}"}, "success": False}
        except Exception as e:
            logger.error(f"Unexpected error in OracleInfo: {str(e)}")
            result = {"result": {"cmdb_collect_error": f"Unexpected error: {str(e)}"}, "success": False}
        finally:
            self.cursor = None
            self.connection = None

        return result


def _row_get(row: Dict[str, Any] | None, key: str, default: Any = "") -> Any:
    if not row:
        return default
    for item_key, value in row.items():
        if str(item_key).lower() == key.lower():
            return "" if value is None else value
    return default


def _upper_sid(value: str) -> str:
    return str(value or "").strip().upper()
