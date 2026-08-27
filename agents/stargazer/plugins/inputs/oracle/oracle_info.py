# -*- coding: utf-8 -*-
"""
Oracle Server Information Collector

A standalone script to gather information about Oracle servers.
"""
from typing import Any, Dict

import oracledb
from sanic.log import logger


class OracleInfo:
    """Class for collecting Oracle instance information."""

    SQL_QUERIES = {
        "version": "SELECT * FROM v$version WHERE rownum=1",
        "max_mem": "SELECT SUM(value) AS TOTAL_MEMORY FROM v$sga",
        "max_conn": "SELECT value FROM v$parameter WHERE name='sessions'",
        "db_name": "SELECT name FROM v$database",
        "database_role": "SELECT database_role FROM v$database",
        "sid": "SELECT INSTANCE_NAME AS SID FROM V$INSTANCE",
    }

    def __init__(self, kwargs: Dict[str, Any]):
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 1521))
        self.user = kwargs.get("user")
        self.password = kwargs.get("password", "")
        self.service_name = kwargs.get("service_name", "orclpdb")
        self.timeout = 20  # 连接超时硬编码；表单 timeout 由框架作单对象预算
        self.info: Dict[str, Any] = {}
        self.connection = None
        self.cursor = None

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

    async def _collect(self):
        """Collect all required Oracle info."""
        logger.info("Starting data collection from Oracle database.")
        try:
            self.info["version"] = (await self._exec_sql(self.SQL_QUERIES["version"])).get("BANNER", "")
            self.info["max_mem"] = str((await self._exec_sql(self.SQL_QUERIES["max_mem"])).get("TOTAL_MEMORY", 0))
            self.info["max_conn"] = str((await self._exec_sql(self.SQL_QUERIES["max_conn"])).get("VALUE", 0))
            self.info["db_name"] = (await self._exec_sql(self.SQL_QUERIES["db_name"])).get("NAME", "")
            self.info["database_role"] = (await self._exec_sql(self.SQL_QUERIES["database_role"])).get("DATABASE_ROLE", "")
            self.info["sid"] = (await self._exec_sql(self.SQL_QUERIES["sid"])).get("SID", "")
            self.info["ip_addr"] = self.host
            self.info["port"] = self.port
            self.info["service_name"] = self.service_name
            self.info["inst_name"] = f"{self.host}-oracle"
        except Exception as e:
            logger.error(f"Error during data collection: {str(e)}")
            raise

    async def list_all_resources(self) -> dict[str, Any]:
        """Public method to collect all info and format it for Prometheus."""
        try:
            async with await oracledb.connect_async(
                user=self.user,
                password=self.password,
                dsn=f"{self.host}:{self.port}/{self.service_name}",
                tcp_connect_timeout=self.timeout,
            ) as connection:
                async with connection.cursor() as cursor:
                    self.cursor = cursor
                    try:
                        await self._collect()
                    except Exception as e:
                        logger.error(f"Error during data collection: {str(e)}")
                        raise

            result = {"result": {"oracle": [self.info]}, "success": True}
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
