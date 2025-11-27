#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
MySQL Server Information Collector

A standalone script to gather information about MySQL servers.
"""

from decimal import Decimal
import pymysql
from pymysql.constants import CLIENT
import json
from plugins.base_utils import convert_to_prometheus_format
from sanic.log import logger


class MysqlInfo:
    """Class for collecting MySQL instance information."""

    def __init__(self, kwargs):
        self.host = kwargs.get('host', 'localhost')
        self.port = int(kwargs.get('port', 3306))
        self.user = kwargs.get('user')
        self.password = kwargs.get('password', '')
        self.database = kwargs.get('database', '')
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
        # self._get_master_status()
        # self._get_slave_status()
        # self._get_slaves()

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
        res = self._exec_sql('SHOW MASTER STATUS')
        if res:
            for line in res:
                for vname, val in line.items():
                    self.info['master_status'][vname] = self._convert(val)

    def _get_slave_status(self):
        """Get slave status if the instance is a slave."""
        res = self._exec_sql('SHOW SLAVE STATUS')
        if res and len(res) > 0:
            line = res[0]  # SHOW SLAVE STATUS returns only one row
            host = line['Master_Host']
            port = line['Master_Port']
            user = line['Master_User']

            if host not in self.info['slave_status']:
                self.info['slave_status'][host] = {}
            if port not in self.info['slave_status'][host]:
                self.info['slave_status'][host][port] = {}
            if user not in self.info['slave_status'][host][port]:
                self.info['slave_status'][host][port][user] = {}

            for vname, val in line.items():
                if vname not in ('Master_Host', 'Master_Port', 'Master_User'):
                    self.info['slave_status'][host][port][user][vname] = self._convert(val)

    def _get_slaves(self):
        """Get slave hosts info if the instance is a master."""
        res = self._exec_sql('SHOW SLAVE HOSTS')
        if res:
            for line in res:
                srv_id = line['Server_id']
                if srv_id not in self.info['slave_hosts']:
                    self.info['slave_hosts'][srv_id] = {}
                for vname, val in line.items():
                    if vname != 'Server_id':
                        self.info['slave_hosts'][srv_id][vname] = self._convert(val)

    def list_all_resources(self):
        """
        Convert collected data to a standard format.
        """
        try:
            excute_res = True
            message = ''
            try:
                self._connect()
                self._collect()
            except Exception as err:
                excute_res = False
                message = str(err)
            if excute_res:
                model_data = {
                    "ip_addr": self.host,
                    "port": self.port,
                    "version": self.info['version']['version'],
                    "enable_binlog": self.info["settings"]["log_bin"],
                    "sync_binlog": self.info["settings"]["sync_binlog"],
                    "max_conn": self.info["settings"]["max_connections"],
                    "max_mem": self.info["settings"]["max_allowed_packet"],
                    "basedir": self.info["settings"]["basedir"],
                    "datadir": self.info["settings"]["datadir"],
                    "socket": self.info["settings"]["socket"],
                    "bind_address": self.info["settings"]["bind_address"],
                    "slow_query_log": self.info["settings"]["slow_query_log"],
                    "slow_query_log_file": self.info["settings"]["slow_query_log_file"],
                    "log_error": self.info["settings"]["log_error"],
                    "wait_timeout": self.info["settings"]["wait_timeout"],
                }
                inst_data = {
                    "result": json.dumps(model_data),
                    "success": excute_res,
                }
                result = convert_to_prometheus_format({"mysql": [inst_data]})
            else:
                inst_data = {
                    "result": message,
                    "success": excute_res,
                }
                result = convert_to_prometheus_format({"mysql": [inst_data]})
            return result
        except Exception as err:
            import traceback
            logger.error(f"mysql_info main error! {traceback.format_exc()}")
        finally:
            self.close()

    def close(self):
        """Close the MySQL connection."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
