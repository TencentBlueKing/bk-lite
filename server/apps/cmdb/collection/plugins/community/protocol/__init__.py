"""Protocol collection plugins."""

from apps.cmdb.collection.plugins.community.protocol.influxdb import InfluxdbCollectionPlugin
from apps.cmdb.collection.plugins.community.protocol.mssql import MssqlCollectionPlugin
from apps.cmdb.collection.plugins.community.protocol.mysql import MysqlCollectionPlugin
from apps.cmdb.collection.plugins.community.protocol.oracle import OracleCollectionPlugin
from apps.cmdb.collection.plugins.community.protocol.postgresql import PostgresqlCollectionPlugin
from apps.cmdb.collection.plugins.community.protocol.ssl_cer import SslCerCollectionPlugin

__all__ = [
	"MysqlCollectionPlugin",
	"InfluxdbCollectionPlugin",
	"PostgresqlCollectionPlugin",
	"OracleCollectionPlugin",
	"MssqlCollectionPlugin",
	"SslCerCollectionPlugin",
]