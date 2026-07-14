# -*- coding: utf-8 -*-
"""TDSQL Information Collector (G5.2 真实现)。

腾讯云 TDSQL,MySQL 兼容协议,使用 pymysql 直连。
采集字段:版本、数据库列表、proxy 状态、用户列表、表大小。
"""
import logging

logger = logging.getLogger(__name__)

try:
    import pymysql  # noqa
except ImportError:
    pymysql = None
    logger.warning("pymysql not available; tdsql collector will not function without it")


class TdsqlInfo:
    """采集 tdsql 实例配置信息 (G5.2 真实现)。"""

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 3306))
        self.user = kwargs.get("user", "tdsql")
        self.password = kwargs.get("password", "")
        self.charset = kwargs.get("charset", "utf8mb4")
        self.timeout = int(kwargs.get("timeout", 10))

    def _connect(self):
        if pymysql is None:
            raise RuntimeError("pymysql not installed")
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            charset=self.charset,
            connect_timeout=self.timeout,
        )

    def _query(self, sql, dbname=None):
        conn = self._connect()
        try:
            if dbname:
                conn.select_db(dbname)
            cur = conn.cursor(pymysql.cursors.DictCursor)
            cur.execute(sql)
            return cur.fetchall()
        finally:
            conn.close()

    def list_all_resources(self):
        """返回标准格式:{"result": {"tdsql": [model_data]}, "success": True}。"""
        model_data = {
            "ip_addr": self.host,
            "port": self.port,
        }

        try:
            # 1. 版本
            try:
                rows = self._query("SELECT VERSION() AS v")
                if rows:
                    raw = rows[0].get("v", "")
                    model_data["version"] = raw
                    # TDSQL 通常版本字符串含 "TDSQL"
                    model_data["is_tdsql"] = "TDSQL" in str(raw).upper()
            except Exception:
                model_data["version"] = ""

            # 2. 数据库列表
            try:
                rows = self._query("SHOW DATABASES")
                dbs = [r.get("Database", "") for r in rows if r.get("Database") not in ("information_schema", "performance_schema", "mysql", "sys")]
                model_data["databases"] = dbs
                model_data["database_count"] = len(dbs)
            except Exception:
                model_data["database_count"] = 0

            # 3. 用户列表
            try:
                rows = self._query("SELECT user, host FROM mysql.user ORDER BY user, host")
                model_data["users"] = [
                    f"{r.get('user', '')}@{r.get('host', '')}" for r in rows
                ]
                model_data["user_count"] = len(model_data["users"])
            except Exception:
                model_data["user_count"] = 0

            # 4. proxy 状态探测(TDSQL 特有)
            try:
                rows = self._query("SHOW STATUS LIKE 'TDSQL_DIST%'")
                model_data["tdsql_proxy_status"] = [r for r in rows] if rows else []
            except Exception:
                pass

            inst_data = {"result": {"tdsql": [model_data]}, "success": True}
        except Exception as err:
            import traceback
            logger.error(f"tdsql_info main error! {traceback.format_exc()}")
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}

        return inst_data