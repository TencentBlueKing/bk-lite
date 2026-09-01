#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
MySQL Server Information Collector

A standalone script to gather information about MySQL servers.
"""

from decimal import Decimal

import aiomysql
from core.collection.contracts import AccessProbeResult, AccessProbeStatus
from core.decorator import timer
from pymysql.constants import CLIENT
from pymysql.err import OperationalError
from sanic.log import logger


class MysqlInfo:
    """Class for collecting MySQL instance information."""

    def __init__(self, kwargs):
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 3306))
        self.user = kwargs.get("user")
        self.password = kwargs.get("password", "")
        self.database = kwargs.get("database", "")
        self.timeout = 10  # 连接超时硬编码；表单 timeout 由框架作单对象预算
        self.client_flag = CLIENT.MULTI_STATEMENTS
        self.info = {
            "version": {},
            "databases": {},
            "settings": {},
            "global_status": {},
            "engines": {},
            "users": {},
            "master_status": {},
            "slave_hosts": {},
            "slave_status": {},
            "replication_errors": {},
        }
        self.connection = None
        self.cursor = None
        self.collection_task_id = kwargs.get("collection_task_id")

    async def _connect(self):
        """Establish MySQL connection."""
        try:
            self.connection = await aiomysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database or None,
                client_flag=self.client_flag,
                connect_timeout=self.timeout,
                autocommit=True,
            )
            self.cursor = await self.connection.cursor(aiomysql.DictCursor)
        except Exception as e:
            raise RuntimeError("Failed to connect to MySQL") from e

    async def probe(self) -> AccessProbeResult:
        try:
            await self._connect()
            rows = await self._exec_sql("SHOW GLOBAL VARIABLES LIKE 'version'")
            version = str(rows[0].get("Value") or "") if rows else ""
            return AccessProbeResult(
                status=AccessProbeStatus.READY,
                evidence={"server_version": version},
            )
        except RuntimeError as error:
            cause = error.__cause__
            error_number = cause.args[0] if cause is not None and cause.args else None
            if error_number == 1045 or (isinstance(cause, OperationalError) and cause.args and cause.args[0] == 1045):
                return AccessProbeResult(
                    status=AccessProbeStatus.AUTH_FAILED,
                    error_code="authentication_failed",
                )
            raise
        finally:
            await self.close()

    async def _exec_sql(self, query):
        """Execute SQL query and return results."""
        try:
            await self.cursor.execute(query)
            return await self.cursor.fetchall()
        except Exception as e:
            raise RuntimeError(f"Error executing SQL '{query}': {str(e)}")

    async def _exec_first_query(self, queries):
        """Execute the first successful SQL query from a list."""
        last_err = None
        for query in queries:
            try:
                return await self._exec_sql(query)
            except Exception as err:
                last_err = err
        raise RuntimeError(str(last_err))

    def _get_first_key(self, data, keys):
        """Get first available key from dict."""
        for key in keys:
            if key in data:
                return data.get(key)
        return None

    def _convert(self, val):
        """Convert unserializable data."""
        try:
            if isinstance(val, Decimal):
                return float(val)
            return int(val)
        except (ValueError, TypeError):
            return val

    async def _collect(self):
        """Collect all possible subsets."""
        await self._get_databases()
        await self._get_global_variables()
        await self._safe_collect("master_status", self._get_master_status)
        await self._safe_collect("slave_status", self._get_slave_status)
        await self._safe_collect("slave_hosts", self._get_slaves)

    async def _safe_collect(self, name, func):
        """Collect optional data without failing the full run."""
        try:
            await func()
        except Exception as err:
            logger.warning("mysql_info collect %s failed: %s", name, str(err))
            self.info["replication_errors"][name] = str(err)

    async def _get_databases(self):
        """Get info about databases."""
        query = 'SELECT table_schema AS "name", ' 'SUM(data_length + index_length) AS "size" ' "FROM information_schema.TABLES GROUP BY table_schema"
        res = await self._exec_sql(query)
        if res:
            for db in res:
                self.info["databases"][db["name"]] = {"size": int(db["size"])}

    async def _get_global_variables(self):
        """Get global variables (instance settings)."""
        res = await self._exec_sql("SHOW GLOBAL VARIABLES")
        if res:
            for var in res:
                self.info["settings"][var["Variable_name"]] = self._convert(var["Value"])

            full = self.info["settings"]["version"]
            self.info["version"] = {"version": full}
            await self._ensure_server_uuid()

    async def _ensure_server_uuid(self):
        """Ensure server_uuid is populated for old versions."""
        if self.info["settings"].get("server_uuid"):
            return
        try:
            res = await self._exec_sql("SELECT @@server_uuid AS server_uuid")
            if res:
                self.info["settings"]["server_uuid"] = res[0].get("server_uuid")
        except Exception as err:
            logger.warning("mysql_info get server_uuid failed: %s", str(err))

    async def _get_master_status(self):
        """Get master status if the instance is a master."""
        res = await self._exec_first_query(
            [
                "SHOW MASTER STATUS",
                "SHOW BINARY LOG STATUS",
            ]
        )
        if res:
            for line in res:
                for vname, val in line.items():
                    self.info["master_status"][vname] = self._convert(val)

    async def _get_slave_status(self):
        """Get slave status if the instance is a slave."""
        res = await self._exec_first_query(
            [
                "SHOW SLAVE STATUS",
                "SHOW REPLICA STATUS",
            ]
        )
        if res and len(res) > 0:
            line = res[0]
            host = self._get_first_key(line, ["Master_Host", "Source_Host"])
            port = self._get_first_key(line, ["Master_Port", "Source_Port"])
            user = self._get_first_key(line, ["Master_User", "Source_User"])

            if host not in self.info["slave_status"]:
                self.info["slave_status"][host] = {}
            if port not in self.info["slave_status"][host]:
                self.info["slave_status"][host][port] = {}
            if user not in self.info["slave_status"][host][port]:
                self.info["slave_status"][host][port][user] = {}

            for vname, val in line.items():
                if vname not in (
                    "Master_Host",
                    "Master_Port",
                    "Master_User",
                    "Source_Host",
                    "Source_Port",
                    "Source_User",
                ):
                    self.info["slave_status"][host][port][user][vname] = self._convert(val)

    async def _get_slaves(self):
        """Get slave hosts info if the instance is a master."""
        res = await self._exec_first_query(
            [
                "SHOW SLAVE HOSTS",
                "SHOW REPLICA HOSTS",
            ]
        )
        if res:
            for line in res:
                srv_id = line["Server_id"]
                if srv_id not in self.info["slave_hosts"]:
                    self.info["slave_hosts"][srv_id] = {}
                for vname, val in line.items():
                    if vname != "Server_id":
                        self.info["slave_hosts"][srv_id][vname] = self._convert(val)

    def _get_replication_info(self):
        """Get replication role and cluster hints."""
        role = "standalone"
        master_host = None
        master_port = None
        master_user = None
        master_uuid = None
        server_uuid = self.info["settings"].get("server_uuid")
        slave_io_running = None
        slave_sql_running = None

        if self.info["slave_status"]:
            role = "slave"
            for host, ports in self.info["slave_status"].items():
                for port, users in ports.items():
                    for user, status in users.items():
                        master_host = host
                        master_port = port
                        master_user = user
                        master_uuid = self._get_first_key(status, ["Master_UUID", "Source_UUID"])
                        slave_io_running = self._get_first_key(status, ["Slave_IO_Running", "Replica_IO_Running"])
                        slave_sql_running = self._get_first_key(status, ["Slave_SQL_Running", "Replica_SQL_Running"])
                        break
                    break
                break
        elif self.info["master_status"] or self.info["slave_hosts"]:
            role = "master"

        has_slaves = bool(self.info["slave_hosts"])
        if role == "slave" and master_uuid:
            cluster_id = master_uuid
        elif role == "master" and server_uuid:
            cluster_id = server_uuid
        elif server_uuid:
            cluster_id = server_uuid
        elif role == "slave" and master_host and master_port is not None:
            cluster_id = f"{master_host}:{master_port}"
        else:
            cluster_id = f"{self.host}:{self.port}"

        return {
            "role": role,
            "cluster_id": cluster_id,
            "master_host": master_host,
            "master_port": master_port,
            "master_user": master_user,
            "master_uuid": master_uuid,
            "server_uuid": server_uuid,
            "has_slaves": has_slaves,
            "slave_io_running": slave_io_running,
            "slave_sql_running": slave_sql_running,
        }

    @timer(logger=logger)
    async def list_all_resources(self):
        """Convert collected data to a standard format."""
        try:
            await self._connect()
            await self._collect()
            model_data = {
                "ip_addr": self.host,
                "port": self.port,
                "version": self.info["version"]["version"],
                "enable_binlog": self.info["settings"].get("log_bin"),
                "sync_binlog": self.info["settings"].get("sync_binlog"),
                "max_conn": self.info["settings"].get("max_connections"),
                "max_mem": self.info["settings"].get("max_allowed_packet"),
                "basedir": self.info["settings"].get("basedir"),
                "datadir": self.info["settings"].get("datadir"),
                "socket": self.info["settings"].get("socket"),
                "bind_address": self.info["settings"].get("bind_address"),
                "slow_query_log": self.info["settings"].get("slow_query_log"),
                "slow_query_log_file": self.info["settings"].get("slow_query_log_file"),
                "log_error": self.info["settings"].get("log_error"),
                "wait_timeout": self.info["settings"].get("wait_timeout"),
            }
            model_data.update(self._get_replication_info())
            inst_data = {"result": {"mysql": [model_data]}, "success": True}
        except Exception as err:  # noqa
            logger.exception(
                "event=mysql_collect_failed host=%s task_id=%s failed_stage=%s error_type=%s",
                self.host,
                self.collection_task_id,
                "list_all_resources",
                type(err).__name__,
            )
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}

        finally:
            await self.close()

        return inst_data

    async def close(self):
        """Close the MySQL connection."""
        if self.cursor:
            await self.cursor.close()
            self.cursor = None
        if self.connection:
            self.connection.close()
            self.connection = None
