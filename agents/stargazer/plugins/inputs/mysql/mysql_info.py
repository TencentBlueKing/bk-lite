#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
MySQL Server Information Collector

A standalone script to gather information about MySQL servers.
"""

from decimal import Decimal
import pymysql
from pymysql.constants import CLIENT

from core.decorator import timer
from sanic.log import logger


class MysqlInfo:
    """Class for collecting MySQL instance information."""

    def __init__(self, kwargs):
        self.host = kwargs.get('host', 'localhost')
        self.port = int(kwargs.get('port', 3306))
        self.user = kwargs.get('user')
        self.password = kwargs.get('password', '')
        self.database = kwargs.get('database', '')
        self.timeout = int(kwargs.get('timeout', 10))
        self.client_flag = CLIENT.MULTI_STATEMENTS
        self.cursorclass = pymysql.cursors.DictCursor
        self.info = {
            'version': {},
            'databases': {},
            'settings': {},
            'global_status': {},
            'engines': {},
            'users': {},
            'master_status': {},
            'slave_hosts': {},
            'slave_status': {},
            'replication_errors': {},
        }
        self.connection = None
        self.cursor = None

        # self._connect()

    def _connect(self):
        """Establish MySQL connection."""
        try:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                client_flag=self.client_flag,
                cursorclass=self.cursorclass,
                connect_timeout=self.timeout,
            )
            self.cursor = self.connection.cursor()
        except Exception as e:
            raise RuntimeError(f"Failed to connect to MySQL: {str(e)}")

    def _exec_sql(self, query):
        """Execute SQL query and return results."""
        try:
            self.cursor.execute(query)
            return self.cursor.fetchall()
        except Exception as e:
            raise RuntimeError(f"Error executing SQL '{query}': {str(e)}")

    def _exec_first_query(self, queries):
        """Execute the first successful SQL query from a list."""
        last_err = None
        for query in queries:
            try:
                return self._exec_sql(query)
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

    def _collect(self):
        """Collect all possible subsets."""
        self._get_databases()
        self._get_global_variables()
        # self._get_global_status()
        # self._get_engines()
        # self._get_users()
        self._safe_collect("master_status", self._get_master_status)
        self._safe_collect("slave_status", self._get_slave_status)
        self._safe_collect("slave_hosts", self._get_slaves)

    def _safe_collect(self, name, func):
        """Collect optional data without failing the full run."""
        try:
            func()
        except Exception as err:
            logger.warning("mysql_info collect %s failed: %s", name, str(err))
            self.info['replication_errors'][name] = str(err)

    def _get_databases(self):
        """Get info about databases."""
        query = ('SELECT table_schema AS "name", '
                 'SUM(data_length + index_length) AS "size" '
                 'FROM information_schema.TABLES GROUP BY table_schema')
        res = self._exec_sql(query)
        if res:
            for db in res:
                self.info['databases'][db['name']] = {'size': int(db['size'])}

    def _get_global_variables(self):
        """Get global variables (instance settings)."""
        res = self._exec_sql('SHOW GLOBAL VARIABLES')
        if res:
            for var in res:
                self.info['settings'][var['Variable_name']] = self._convert(var['Value'])

            full = self.info['settings']['version']
            self.info['version'] = {"version": full}
            self._ensure_server_uuid()

    def _ensure_server_uuid(self):
        """Ensure server_uuid is populated for old versions."""
        if self.info['settings'].get("server_uuid"):
            return
        try:
            res = self._exec_sql('SELECT @@server_uuid AS server_uuid')
            if res:
                self.info['settings']['server_uuid'] = res[0].get('server_uuid')
        except Exception as err:
            logger.warning("mysql_info get server_uuid failed: %s", str(err))

    def _get_global_status(self):
        """Get global status."""
        res = self._exec_sql('SHOW GLOBAL STATUS')
        if res:
            for var in res:
                self.info['global_status'][var['Variable_name']] = self._convert(var['Value'])

    def _get_engines(self):
        """Get storage engines info."""
        res = self._exec_sql('SHOW ENGINES')
        if res:
            for line in res:
                engine = line['Engine']
                self.info['engines'][engine] = {k: v for k, v in line.items() if k != 'Engine'}

    def _get_users(self):
        """Get user info."""
        res = self._exec_sql('SELECT * FROM mysql.user')
        if res:
            for line in res:
                host = line['Host']
                user = line['User']

                if host not in self.info['users']:
                    self.info['users'][host] = {}

                self.info['users'][host][user] = {
                    k: self._convert(v)
                    for k, v in line.items()
                    if k not in ('Host', 'User')
                }

    def _get_master_status(self):
        """Get master status if the instance is a master."""
        res = self._exec_first_query([
            'SHOW MASTER STATUS',
            'SHOW BINARY LOG STATUS',
        ])
        if res:
            for line in res:
                for vname, val in line.items():
                    self.info['master_status'][vname] = self._convert(val)

    def _get_slave_status(self):
        """Get slave status if the instance is a slave."""
        res = self._exec_first_query([
            'SHOW SLAVE STATUS',
            'SHOW REPLICA STATUS',
        ])
        if res and len(res) > 0:
            line = res[0]  # SHOW SLAVE STATUS returns only one row
            host = self._get_first_key(line, ["Master_Host", "Source_Host"])
            port = self._get_first_key(line, ["Master_Port", "Source_Port"])
            user = self._get_first_key(line, ["Master_User", "Source_User"])

            if host not in self.info['slave_status']:
                self.info['slave_status'][host] = {}
            if port not in self.info['slave_status'][host]:
                self.info['slave_status'][host][port] = {}
            if user not in self.info['slave_status'][host][port]:
                self.info['slave_status'][host][port][user] = {}

            for vname, val in line.items():
                if vname not in (
                    'Master_Host', 'Master_Port', 'Master_User',
                    'Source_Host', 'Source_Port', 'Source_User',
                ):
                    self.info['slave_status'][host][port][user][vname] = self._convert(val)

    def _get_slaves(self):
        """Get slave hosts info if the instance is a master."""
        res = self._exec_first_query([
            'SHOW SLAVE HOSTS',
            'SHOW REPLICA HOSTS',
        ])
        if res:
            for line in res:
                srv_id = line['Server_id']
                if srv_id not in self.info['slave_hosts']:
                    self.info['slave_hosts'][srv_id] = {}
                for vname, val in line.items():
                    if vname != 'Server_id':
                        self.info['slave_hosts'][srv_id][vname] = self._convert(val)

    def _get_replication_info(self):
        """Get replication role and cluster hints."""
        role = "standalone"
        master_host = None
        master_port = None
        master_user = None
        master_uuid = None
        server_uuid = self.info['settings'].get("server_uuid")
        slave_io_running = None
        slave_sql_running = None

        if self.info['slave_status']:
            role = "slave"
            for host, ports in self.info['slave_status'].items():
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
        elif self.info['master_status'] or self.info['slave_hosts']:
            role = "master"

        has_slaves = bool(self.info['slave_hosts'])
        cluster_id = None
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
    def list_all_resources(self):
        """
        Convert collected data to a standard format.
        """
        try:
            self._connect()
            self._collect()
            model_data = {
                "ip_addr": self.host,
                "port": self.port,
                "version": self.info['version']['version'],
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
            import traceback
            logger.error(f"mysql_info main error! {traceback.format_exc()}")
            inst_data = {"result": {"cmdb_collect_error": str(err)}, "success": False}

        finally:
            self.close()

        return inst_data

    def close(self):
        """Close the MySQL connection."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
