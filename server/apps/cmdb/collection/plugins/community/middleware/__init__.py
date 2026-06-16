"""Middleware collection plugins."""

from apps.cmdb.collection.plugins.community.middleware.activemq import ActivemqCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.apache import ApacheCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.ceph import CephCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.consul import ConsulCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.docker import DockerCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.etcd import EtcdCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.haproxy import HaproxyCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.iis import IisCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.jboss import JbossCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.jetty import JettyCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.kafka import KafkaCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.keepalived import KeepalivedCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.memcached import MemcachedCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.minio import MinioCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.nginx import NginxCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.openresty import OpenrestyCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.rabbitmq import RabbitmqCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.rocketmq import RocketmqCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.spark import SparkCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.squid import SquidCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.tomcat import TomcatCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.tongweb import TongwebCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.tuxedo import TuxedoCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.weblogic import WeblogicCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.websphere import WebsphereCollectionPlugin
from apps.cmdb.collection.plugins.community.middleware.zookeeper import ZookeeperCollectionPlugin

__all__ = [
    "NginxCollectionPlugin",
    "ZookeeperCollectionPlugin",
    "KafkaCollectionPlugin",
    "EtcdCollectionPlugin",
    "RabbitmqCollectionPlugin",
    "TomcatCollectionPlugin",
    "ConsulCollectionPlugin",
    "DockerCollectionPlugin",
    "ApacheCollectionPlugin",
    "ActivemqCollectionPlugin",
    "CephCollectionPlugin",
    "HaproxyCollectionPlugin",
    "IisCollectionPlugin",
    "JbossCollectionPlugin",
    "WeblogicCollectionPlugin",
    "KeepalivedCollectionPlugin",
    "MemcachedCollectionPlugin",
    "MinioCollectionPlugin",
    "OpenrestyCollectionPlugin",
    "RocketmqCollectionPlugin",
    "SparkCollectionPlugin",
    "SquidCollectionPlugin",
    "TongwebCollectionPlugin",
    "TuxedoCollectionPlugin",
    "WebsphereCollectionPlugin",
    "JettyCollectionPlugin",
]
