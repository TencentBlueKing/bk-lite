import logging
import os
from apps.node_mgmt.models import Collector, CollectorConfiguration

logger = logging.getLogger("app")


default_sidecar_mode = os.getenv("SIDECAR_INPUT_MODE", "nats")
TELEGRAF_CONFIG = """
[global_tags]
    agent_id="${node.ip}-${node.cloud_region}"

[agent]
    interval = "10s"
    round_interval = true
    metric_batch_size = 1000
    metric_buffer_limit = 10000
    collection_jitter = "0s"
    flush_interval = "30s"
    flush_jitter = "0s"
    precision = "0s"
    hostname = "${node.ip}"
    omit_hostname = false

[[inputs.internal]]
    tags = { "instance_id"="${node.ip}-${node.cloud_region}","instance_type"="internal","instance_name"="${node.name}" }
"""

if default_sidecar_mode == "telegraf":
    TELEGRAF_CONFIG += """
[[outputs.kafka]]
brokers = ["${KAFKA_HOST}:${KAFKA_PORT}"]
topic = "${KAFKA_METRICS_TOPIC}"
sasl_username = "${KAFKA_USERNAME}"
sasl_password = "${KAFKA_PASSWORD}"
sasl_mechanism = "PLAIN"
max_message_bytes = 10000000
compression_codec=1
"""

if default_sidecar_mode == "nats":
    TELEGRAF_CONFIG += """
[[outputs.nats]]
servers = ["${NATS_SERVERS}"]
username = "${NATS_USERNAME}"
password = "${NATS_PASSWORD}"
subject = "metrics.${node.ip_filter}"
data_format = "influx"
"""

if default_sidecar_mode == "vm":
    TELEGRAF_CONFIG += """
[[outputs.influxdb]]
  urls = ["${VM_SERVERS}"]
  database = "victoriametrics"
  skip_database_creation = true
  exclude_retention_policy_tag = true
  content_encoding = "gzip"
"""


def create_telegraf_config(node):
    """创建默认的 Telegraf 配置"""
    try:
        collector_obj = Collector.objects.filter(
            name='Telegraf', node_operating_system=node.operating_system
        ).first()
        configuration = CollectorConfiguration.objects.create(
            name=f'telegraf-{node.id}',
            collector=collector_obj,
            config_template=TELEGRAF_CONFIG,
            is_pre=True,
        )
        configuration.nodes.add(node)
    except Exception as e:
        logger.error(f"create node {node.id} Telegraf default configuration failed {e}")
