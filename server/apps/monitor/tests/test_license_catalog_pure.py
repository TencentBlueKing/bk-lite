import pytest

from apps.monitor.constants.license_catalog import MONITOR_LICENSE_OBJECT_NAMES

EXPECTED_MONITOR_LICENSE_OBJECT_NAMES = frozenset(
    {
        "Host",
        "Hardware Server",
        "Mysql",
        "Postgres",
        "Redis",
        "MongoDB",
        "MSSQL",
        "ElasticSearch",
        "InfluxDB",
        "Oracle",
        "DB2",
        "Dameng",
        "GBase8a",
        "Greenplum",
        "HANA",
        "IRIS",
        "KingBase",
        "OceanBase",
        "OpenGauss",
        "PolarDB PG",
        "Sybase",
        "TiDB",
        "TongRDS",
        "VastBase",
        "Kafka",
        "ActiveMQ",
        "RabbitMQ",
        "Zookeeper",
        "Etcd",
        "Consul",
        "Nginx",
        "Apache",
        "Tomcat",
        "Haproxy",
        "Minio",
        "JVM",
        "Active Directory",
        "Exchange",
        "BES",
        "IBMMQ",
        "JBoss",
        "Jetty",
        "Nacos",
        "TongLINKQ-D",
        "TongLink",
        "TongLinkQ",
        "TongWeb",
        "WebLogic",
        "WebSphere",
        "Docker",
        "Node",
        "K3SNode",
        "ESXI",
        "VM",
        "CVM",
        "ECS",
        "CNwareHost",
        "CNwareVM",
        "SangforSCPHost",
        "SangforSCPVM",
        "Storage",
        "Switch",
        "Router",
        "Firewall",
        "Loadbalance",
        "Access",
        "Wireless",
        "Transmission",
        "VoiceGateway",
        "ConsoleServer",
        "NetworkService",
        "Ping",
        "TCPPort",
        "Website",
    }
)


@pytest.mark.unit
def test_monitor_license_catalog_includes_assets_and_excludes_derivatives():
    assert MONITOR_LICENSE_OBJECT_NAMES == EXPECTED_MONITOR_LICENSE_OBJECT_NAMES

    assert "Pod" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "Cluster" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "K3SCluster" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "K3SPod" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "Docker Container" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "vCenter" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "DataStorage" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "TCP" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "MinIO" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "Aliyun" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "CNware" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "SangforSCP" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "CNwareStoragePool" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "AliyunKafka" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "RDSMySQL" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "Process" not in MONITOR_LICENSE_OBJECT_NAMES
    assert "VLLM" not in MONITOR_LICENSE_OBJECT_NAMES
