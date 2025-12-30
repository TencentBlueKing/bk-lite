# -*- coding: utf-8 -*-
"""
Oracle Server Information Collector

A standalone script to gather information about Oracle servers.
"""
import oracledb
from sanic.log import logger
from typing import Dict, Any


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
        self.timeout = int(kwargs.get("timeout", 20))
        self.info: Dict[str, Any] = {}
        self.connection = None
        self.cursor = None

    def _exec_sql(self, query: str) -> Dict[str, Any]:
        """Execute SQL query and return results as dict (first row only)."""
        try:
            logger.debug(f"Executing SQL query: {query}")
            self.cursor.execute(query)
            cols = [col[0] for col in self.cursor.description]
            row = self.cursor.fetchone()
            if row:
                return dict(zip(cols, row))
            return {}
        except oracledb.Error as e:
            logger.error(f"Error executing SQL '{query}': {str(e)}")
            raise RuntimeError(f"SQL execution error: {str(e)}")

    def _collect(self):
        """Collect all required Oracle info."""
        logger.info("Starting data collection from Oracle database.")
        try:
            self.info["version"] = self._exec_sql(self.SQL_QUERIES["version"]).get("BANNER", "")
            self.info["max_mem"] = str(self._exec_sql(self.SQL_QUERIES["max_mem"]).get("TOTAL_MEMORY", 0))
            self.info["max_conn"] = str(self._exec_sql(self.SQL_QUERIES["max_conn"]).get("VALUE", 0))
            self.info["db_name"] = self._exec_sql(self.SQL_QUERIES["db_name"]).get("NAME", "")
            self.info["database_role"] = self._exec_sql(self.SQL_QUERIES["database_role"]).get("DATABASE_ROLE", "")
            self.info["sid"] = self._exec_sql(self.SQL_QUERIES["sid"]).get("SID", "")
            self.info["ip_addr"] = self.host
            self.info["port"] = self.port
            self.info["service_name"] = self.service_name
            self.info["inst_name"] = f"{self.host}-oracle"
        except Exception as e:
            logger.error(f"Error during data collection: {str(e)}")
            raise

    def list_all_resources(self) -> dict[str, Any]:
        """Public method to collect all info and format it for Prometheus."""
        try:
            # 使用上下文管理器确保资源自动关闭
            with oracledb.connect(
                    user=self.user,
                    password=self.password,
                    dsn=f"{self.host}:{self.port}/{self.service_name}",
                    tcp_connect_timeout=self.timeout
            ) as connection:
                with connection.cursor() as cursor:
                    self.cursor = cursor
                    try:
                        self._collect()
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
            # 确保实例变量被清理
            self.cursor = None
            self.connection = None

        return result
