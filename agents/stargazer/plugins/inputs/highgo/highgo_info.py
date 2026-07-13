# -*- coding: utf-8 -*-
"""Highgo Information Collector (G5.2 真实现)。

瀚高数据库,PostgreSQL 兼容协议,使用 psycopg2 直连。
采集字段:版本、数据库列表、用户列表、扩展列表。
"""
import logging

logger = logging.getLogger(__name__)

try:
    import psycopg2  # noqa
except ImportError:
    psycopg2 = None
    logger.warning("psycopg2 not available; highgo collector will not function without it")


class HighgoInfo:
    """采集 highgo 实例配置信息 (G5.2 真实现)。"""

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 5866))
        self.user = kwargs.get("user", "highgo")
        self.password = kwargs.get("password", "")
        self.database = kwargs.get("database", "highgo")
        self.timeout = int(kwargs.get("timeout", 10))

    def _connect(self, dbname=None):
        if psycopg2 is None:
            raise RuntimeError("psycopg2 not installed")
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            dbname=dbname or self.database,
            connect_timeout=self.timeout,
        )

    def _query(self, sql, dbname=None):
        conn = self._connect(dbname=dbname)
        try:
            cur = conn.cursor()
            cur.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
            return [dict(zip(cols, row)) for row in rows]
        finally:
            conn.close()

    def list_all_resources(self):
        """返回标准格式:{"result": {"highgo": [model_data]}, "success": True}。"""
        model_data = {
            "ip_addr": self.host,
            "port": self.port,
        }

        try:
            # 1. 版本
            try:
                rows = self._query("SELECT version() AS v")
                if rows:
                    model_data["version"] = rows[0].get("v", "")
            except Exception:
                model_data["version"] = ""

            # 2. 数据库列表(排除 template)
            try:
                rows = self._query(
                    "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname"
                )
                model_data["databases"] = [r.get("datname", "") for r in rows]
                model_data["database_count"] = len(model_data["databases"])
            except Exception:
                model_data["database_count"] = 0

            # 3. 用户列表
            try:
                rows = self._query("SELECT usename FROM pg_user ORDER BY usename")
                model_data["users"] = [r.get("usename", "") for r in rows]
                model_data["user_count"] = len(model_data["users"])
            except Exception:
                model_data["user_count"] = 0

            # 4. 扩展列表
            try:
                rows = self._query("SELECT extname FROM pg_extension ORDER BY extname")
                model_data["extensions"] = [r.get("extname", "") for r in rows]
            except Exception:
                pass

            inst_data = {"result": {"highgo": [model_data]}, "success": True}
        except Exception as err:
            import traceback
            logger.error(f"highgo_info main error! {traceback.format_exc()}")
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}

        return inst_data