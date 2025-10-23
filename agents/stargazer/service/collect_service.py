# -- coding: utf-8 --
# @File: collect_service.py
# @Time: 2025/2/27 11:29
# @Author: windyzhao
import time
import traceback
import importlib
from asyncio import iscoroutinefunction

from sanic.log import logger


class CollectService(object):
    def __init__(self, params: dict):
        self.params = params
        self.plugin_name = self.params.pop("plugin_name")
        self.plugin_name_map = {
            "vmware_info": "VmwareManage",
            "snmp_facts": "SnmpFacts",
            "snmp_topo": "SnmpTopoClient",
            "mysql_info": "MysqlInfo",
            "aliyun_info": "CwAliyun",
            "host_info": "HostInfo",
            "redis_info": "RedisInfo",
            "nginx_info": "NginxInfo",
            "zookeeper_info": "ZookeeperInfo",
            "kafka_info": "KafkaInfo",
            "qcloud_info": "TencentCloudManager",
            "etcd_info": "EtcdInfo",
            "rabbitmq_info": "RabbitMQInfo",
            "tomcat_info": "TomcatInfo",
            "es_info": "ESInfo",
            "mongodb_info": "MongoDBInfo",
            "apache_info": "ApacheInfo",
            "activemq_info": "ActiveMQInfo",
            "pgsql_info": "PgsqlInfo",
            "weblogic_info": "WebLogicInfo",
            "keepalived_info": "KeepalivedInfo",
            "tongweb_info": "TongWebInfo",
            "dameng_info": "DaMengInfo",
            "oracle_info": "OracleInfo",
            "db2_info": "DB2Info",
            "tidb_info": "TiDBInfo",
            "jetty_info": "JettyInfo",
            "hbase_info": "HBaseInfo",
            "mssql_info": "MSSQLInfo",
        }

    def import_plugin(self, plugin_name):
        """
        动态加载插件
        :param plugin_name: 插件名称
        :return: 插件类
        """
        try:
            module = importlib.import_module(f'plugins.{plugin_name}')
            plugin_class = getattr(module, self.plugin_name_map[plugin_name])
            return plugin_class
        except ImportError as e:
            logger.error(f"Error importing plugin {plugin_name}: {e}")
            raise

    async def execute(self, func, *args, **kwargs):
        """
        通用执行方法，兼容同步和异步方法。
        """
        if iscoroutinefunction(func):
            # 如果是异步方法，使用 await 调用
            return await func(*args, **kwargs)
        else:
            # 如果是同步方法，直接调用
            return func(*args, **kwargs)

    async def collect(self):
        try:
            # 动态加载插件
            plugin_class = self.import_plugin(self.plugin_name)
            plugin_instance = plugin_class(self.params)
            # 调用 list_all_resources，兼容同步和异步
            result = await self.execute(plugin_instance.list_all_resources)
            return result
        except Exception as e:
            logger.info(f"Error loading plugin {self.plugin_name}: {traceback.format_exc()}")
            # 生成错误指标数据，直接转换为Prometheus文本格式
            current_timestamp = int(time.time() * 1000)  # 毫秒时间戳
            error_type = str(type(e).__name__)

            # 直接构造Prometheus格式字符串
            prometheus_lines = ["# HELP collection_status Auto-generated help for collection_status",
                                "# TYPE collection_status gauge"]
            # 添加采集状态指标
            status_metric = f'collection_status{{plugin="{self.plugin_name}",status="error",error_type="{error_type}"}} 1 {current_timestamp}'
            prometheus_lines.append(status_metric)

            # 确保最后以换行符结尾
            return "\n".join(prometheus_lines) + "\n"

    def list_regions(self):
        try:
            plugin_class = self.import_plugin(self.plugin_name)
            plugin_instance = plugin_class(self.params)
            result = plugin_instance.list_regions()
            return {"result": result, "success": True}
        except Exception as e:
            logger.info(f"Error list_regions plugin {self.plugin_name}: {traceback.format_exc()}")
            # 生成错误指标数据，直接转换为Prometheus文本格式
            return {"result": [], "success": False}
