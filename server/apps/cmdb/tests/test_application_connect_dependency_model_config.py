"""应用 connect 数据库/中间件/云上同类的模型种子。"""

from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.unit

XLSX = Path(__file__).resolve().parents[1] / "support-files" / "model_config.xlsx"

APPLICATION_CONNECT_TARGETS = frozenset(
    {
        "mysql",
        "oracle",
        "mssql",
        "redis",
        "mongodb",
        "es",
        "postgresql",
        "db2",
        "tidb",
        "dameng",
        "hbase",
        "influxdb",
        "opengauss",
        "kingbase",
        "vastbase",
        "greenplum",
        "gbase8a",
        "oceanbase",
        "highgo",
        "informix",
        "sybase",
        "couchbase",
        "mycat",
        "sap_hana",
        "iris",
        "redis_sentinel",
        "gbase8s",
        "oscar",
        "tongrds",
        "tdsql",
        "kafka",
        "zookeeper",
        "rabbitmq",
        "activemq",
        "etcd",
        "memcached",
        "rocketmq",
        "ceph",
        "minio",
        "nacos",
        "ibmmq",
        "tonglinkq",
        "aliyun_mysql",
        "aliyun_pgsql",
        "aliyun_redis",
        "aliyun_mongodb",
        "aliyun_kafka_inst",
        "qcloud_mysql",
        "qcloud_rocketmq",
        "qcloud_redis",
        "qcloud_mongodb",
        "qcloud_pgsql",
        "qcloud_plusar_cluster",
        "qcloud_cmq",
        "qcloud_cmq_topic",
        "aws_rds",
        "aws_msk",
        "aws_elasticache",
        "aws_docdb",
        "aws_memdb",
        "hwcloud_rds",
        "hwcloud_dcs",
        "azure_redis",
        "azure_mysql",
    }
)

APPLICATION_CONNECT_EXCLUDED = frozenset(
    {
        "host",
        "apache",
        "tomcat",
        "nginx",
        "iis",
        "weblogic",
        "websphere",
        "tongweb",
        "keepalive",
        "tuxedo",
        "jetty",
        "openresty",
        "jboss",
        "squid",
        "haproxy",
        "spark",
        "ihs",
        "cics",
        "bes",
        "apusic",
        "inforsuite_as",
        "tonggtp",
        "hdfs",
        "yarn",
        "storm",
        "ambari",
        "oracle_instance",
        "oracle_pdb",
        "oceanbase_zone",
        "oceanbase_server",
        "oceanbase_tenant",
        "nacos_node",
        "nacos_namespace",
        "nacos_service",
        "ibmmq_channel",
        "ibmmq_listener",
        "ibmmq_localqueue",
        "ibmmq_remotequeue",
    }
)


def _rows(sheet_name):
    return pd.read_excel(XLSX, sheet_name=sheet_name, header=1).fillna("")


def test_application_keeps_run_host_and_connects_dependencies():
    rows = _rows("asso-application")
    pairs = {(row.src_model_id, row.dst_model_id, row.asst_id, row.mapping) for row in rows.itertuples()}
    assert ("application", "host", "run", "n:n") in pairs
    connect_dst = {dst for src, dst, asst, mapping in pairs if src == "application" and asst == "connect" and mapping == "n:n"}
    assert connect_dst == APPLICATION_CONNECT_TARGETS
    assert connect_dst.isdisjoint(APPLICATION_CONNECT_EXCLUDED)


def test_application_connect_targets_exist_as_models():
    models = set(_rows("models")["model_id"])
    missing = sorted(APPLICATION_CONNECT_TARGETS - models)
    assert missing == []
