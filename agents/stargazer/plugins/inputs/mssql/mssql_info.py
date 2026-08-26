# -*- coding: utf-8 -*-
"""
MSSQL Server Information Collector

A standalone script to gather information about MSSQL servers.
"""
from typing import Any, Dict

import aioodbc
from core.decorator import timer
from sanic.log import logger


class MSSQLInfo:
    """Class for collecting MSSQL instance information."""

    SQL_QUERIES = {
        "version": "SELECT CAST(SERVERPROPERTY('ProductVersion') AS NVARCHAR(50)) AS version",
        "max_conn": "SELECT CAST(value_in_use AS INT) AS max_conn FROM sys.configurations WHERE name='user connections'",
        "fill_factor": "SELECT CAST(value AS INT) AS fill_factor FROM sys.configurations WHERE name='fill factor (%)'",
        "boot_account": "SELECT TOP 1 service_account AS boot_account FROM sys.dm_server_services WHERE servicename LIKE 'SQL Server (%'",
        "max_mem": "SELECT physical_memory_in_use_kb / 1024 AS max_mem_mb FROM sys.dm_os_process_memory",
        "order_rule": "SELECT collation_name AS order_rule FROM sys.databases WHERE database_id = DB_ID()",
    }

    def __init__(self, kwargs: Dict[str, Any]):
        self.host = kwargs.get("host", "localhost")
        self.port = kwargs.get("port", 1433)
        self.user = kwargs.get("user")
        self.password = kwargs.get("password")
        self.database = kwargs.get("database")
        self.timeout = 5  # 连接超时硬编码；表单 timeout 由框架作单对象预算
        self.info: Dict[str, Any] = {}
        self.connection = None
        self.cursor = None

    async def _connect(self):
        """Establish MSSQL connection."""
        try:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={self.host},{self.port};"
                f"DATABASE={self.database};"
                f"UID={self.user};"
                f"PWD={self.password}"
            )
            self.connection = await aioodbc.connect(dsn=conn_str, timeout=self.timeout, autocommit=True)
            self.cursor = await self.connection.cursor()
            logger.info(f"Connected to MSSQL database at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to MSSQL: {str(e)}")
            raise RuntimeError(f"Connection error: {str(e)}")

    async def close(self):
        """Close MSSQL connection and cursor."""
        try:
            if self.cursor:
                await self.cursor.close()
                self.cursor = None
            if self.connection:
                await self.connection.close()
                self.connection = None
            logger.info("MSSQL connection closed successfully.")
        except Exception as e:
            logger.warning(f"Error closing MSSQL connection: {str(e)}")

    async def _exec_sql(self, query: str) -> Dict[str, Any]:
        """Execute SQL query and return first row as dict."""
        try:
            logger.debug(f"Executing SQL query: {query}")
            await self.cursor.execute(query)
            row = await self.cursor.fetchone()
            if row:
                return dict(zip([desc[0] for desc in self.cursor.description], row))
            return {}
        except Exception as e:
            logger.error(f"Error executing SQL '{query}': {str(e)}")
            raise RuntimeError(f"SQL execution error: {str(e)}")

    async def _collect(self):
        """Collect all required MSSQL info."""
        logger.info("Starting data collection from MSSQL database.")
        try:
            self.info["ip_addr"] = self.host
            self.info["port"] = self.port
            self.info["db_name"] = self.database
            self.info["version"] = (await self._exec_sql(self.SQL_QUERIES["version"])).get("version", "")
            self.info["max_conn"] = str((await self._exec_sql(self.SQL_QUERIES["max_conn"])).get("max_conn", 0))
            self.info["max_mem"] = str((await self._exec_sql(self.SQL_QUERIES["max_mem"])).get("max_mem_mb", 0))
            self.info["order_rule"] = (await self._exec_sql(self.SQL_QUERIES["order_rule"])).get("order_rule", "")
            self.info["fill_factor"] = str((await self._exec_sql(self.SQL_QUERIES["fill_factor"])).get("fill_factor", 0))
            self.info["boot_account"] = (await self._exec_sql(self.SQL_QUERIES["boot_account"])).get("boot_account", "")
            self.info["inst_name"] = f"{self.host}-mssql-{self.port}"
        except Exception as e:
            logger.error(f"Error during data collection: {str(e)}")
            raise

    @timer(logger=logger)
    async def list_all_resources(self):
        """Public method to collect all info and format it for Prometheus."""
        try:
            await self._connect()
            await self._collect()
            result = {"result": {"mssql": [self.info]}, "success": True}
            logger.info("Data collection completed successfully.")
        except Exception as e:
            logger.error(f"MSSQLInfo list_all_resources error: {str(e)}")
            result = {"result": {"cmdb_collect_error": str(e)}, "success": False}

        finally:
            await self.close()

        return result
