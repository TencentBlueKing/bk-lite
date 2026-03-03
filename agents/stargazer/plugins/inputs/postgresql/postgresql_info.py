#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
PostgreSQL Server Information Collector

Collects core configuration metrics via psycopg2.
"""

from decimal import Decimal
from typing import Any, Dict

import psycopg2
from psycopg2.extras import RealDictCursor

from core.decorator import timer
from sanic.log import logger


class PostgresqlInfo:
    def __init__(self, kwargs):
        self.host = kwargs.get('host', 'localhost')
        self.port = int(kwargs.get('port', 5432))
        self.user = kwargs.get('user')
        self.password = kwargs.get('password', '')
        self.database = kwargs.get('database', 'postgres')
        self.timeout = int(kwargs.get('timeout', 10))
        self.info: Dict[str, Any] = {}
        self.connection = None
        self.cursor = None

    def _connect(self):
        try:
            self.connection = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                dbname=self.database,
                connect_timeout=self.timeout,
            )
            self.cursor = self.connection.cursor(cursor_factory=RealDictCursor)
        except Exception as e:  # noqa
            raise RuntimeError(f"Failed to connect to PostgreSQL: {str(e)}")

    def _exec_sql(self, query):
        try:
            self.cursor.execute(query)
            return self.cursor.fetchall()
        except Exception as e:  # noqa
            raise RuntimeError(f"Error executing SQL '{query}': {str(e)}")

    def _convert(self, value):
        if value is None:
            return value
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, str):
            return value.strip()
        try:
            return int(value)
        except (ValueError, TypeError):
            return value

    def _collect(self):
        queries = {
            'version': "SHOW server_version",
            'config': "SHOW config_file",
            'data_directory': "SHOW data_directory",
            'max_connections': "SHOW max_connections",
            'shared_buffers': "SHOW shared_buffers",
            'log_directory': "SHOW log_directory",
        }
        for key, sql in queries.items():
            result = self._exec_sql(sql)
            if result:
                self.info[key] = list(result[0].values())[0]

    def _shared_buffers_mb(self):
        value = self.info.get('shared_buffers', '')
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            lower = value.lower().strip()
            multiplier = 1
            if lower.endswith('kb'):
                multiplier = 1 / 1024
            elif lower.endswith('mb'):
                multiplier = 1
            elif lower.endswith('gb'):
                multiplier = 1024
            number = ''.join(filter(lambda x: (x.isdigit() or x == '.'), lower))
            try:
                return int(float(number) * multiplier)
            except ValueError:
                return 0
        return 0

    def _log_directory_path(self):
        log_directory = self.info.get('log_directory', '')
        data_directory = self.info.get('data_directory', '')
        if not log_directory:
            return ''
        if log_directory.startswith('/'):
            return log_directory
        return f"{data_directory.rstrip('/')}/{log_directory}" if data_directory else log_directory

    @timer(logger=logger)
    def list_all_resources(self):
        try:
            self._connect()
            self._collect()
            model_data = {
                'inst_name': f"{self.host}-pg-{self.port}",
                'ip_addr': self.host,
                'port': self.port,
                'version': self.info.get('version', ''),
                'conf_path': self.info.get('config', ''),
                'data_path': self.info.get('data_directory', ''),
                'max_conn': self._convert(self.info.get('max_connections', 0)),
                'cache_memory_mb': self._shared_buffers_mb(),
                'log_path': self._log_directory_path(),
            }
            inst_data = {'result': {'postgresql': [model_data]}, 'success': True}
        except Exception as err:  # noqa
            import traceback
            logger.error(f"postgresql_info main error! {traceback.format_exc()}")
            inst_data = {'result': {'cmdb_collect_error': str(err)}, 'success': False}
        finally:
            self.close()
        return inst_data

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
