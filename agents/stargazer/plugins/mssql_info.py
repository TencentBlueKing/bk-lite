# -*- coding: utf-8 -*-
"""
MSSQL Server Information Collector

A standalone script to gather information about MSSQL servers.
"""
import pyodbc
from sanic.log import logger
from typing import Dict, Any
from plugins.base_utils import convert_to_prometheus_format


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
        self.info: Dict[str, Any] = {}
        self.connection = None
        self.cursor = None

    def _connect(self):
        """Establish MSSQL connection."""
        try:
            conn_str = (
                f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                f"SERVER={self.host},{self.port};"
                f"DATABASE={self.database};"
                f"UID={self.user};"
                f"PWD={self.password}"
            )
            self.connection = pyodbc.connect(conn_str, timeout=5)
            self.cursor = self.connection.cursor()
            logger.info(f"Connected to MSSQL database at {self.host}:{self.port}")
        except pyodbc.Error as e:
            logger.error(f"Failed to connect to MSSQL: {str(e)}")
            raise RuntimeError(f"Connection error: {str(e)}")

    def close(self):
        """Close MSSQL connection and cursor."""
        try:
            if self.cursor:
                self.cursor.close()
            if self.connection:
                self.connection.close()
            logger.info("MSSQL connection closed successfully.")
        except pyodbc.Error as e:
            logger.warning(f"Error closing MSSQL connection: {str(e)}")

    def _exec_sql(self, query: str) -> Dict[str, Any]:
        """Execute SQL query and return first row as dict."""
        try:
            logger.debug(f"Executing SQL query: {query}")
            self.cursor.execute(query)
            row = self.cursor.fetchone()
            if row:
                return dict(zip([desc[0] for desc in self.cursor.description], row))
            return {}
        except pyodbc.Error as e:
            logger.error(f"Error executing SQL '{query}': {str(e)}")
            raise RuntimeError(f"SQL execution error: {str(e)}")

    def _collect(self):
        """Collect all required MSSQL info."""
        logger.info("Starting data collection from MSSQL database.")
        try:
            self.info["ip_addr"] = self.host
            self.info["port"] = self.port
            self.info["db_name"] = self.database
            self.info["version"] = self._exec_sql(self.SQL_QUERIES["version"]).get("version", "")
            self.info["max_conn"] = str(self._exec_sql(self.SQL_QUERIES["max_conn"]).get("max_conn", 0))
            self.info["max_mem"] = str(self._exec_sql(self.SQL_QUERIES["max_mem"]).get("max_mem_mb", 0))
            self.info["order_rule"] = self._exec_sql(self.SQL_QUERIES["order_rule"]).get("order_rule", "")
            self.info["fill_factor"] = str(self._exec_sql(self.SQL_QUERIES["fill_factor"]).get("fill_factor", 0))
            self.info["boot_account"] = self._exec_sql(self.SQL_QUERIES["boot_account"]).get("boot_account", "")
            self.info["inst_name"] = f"{self.host}-mssql-{self.port}"
        except Exception as e:
            logger.error(f"Error during data collection: {str(e)}")
            raise

    def list_all_resources(self) -> str:
        """Public method to collect all info and format it for Prometheus."""
        try:
            self._connect()
            self._collect()
            result = convert_to_prometheus_format({"mssql": [self.info]})
            logger.info("Data collection completed successfully.")
            return result
        except Exception as e:
            logger.error(f"MSSQLInfo list_all_resources error: {str(e)}")
        finally:
            self.close()

