import logging

from apps.node_mgmt.models import Collector, CollectorConfiguration

logger = logging.getLogger("app")


NATS_EXECUTOR_CONFIG = """
nats_urls: "${NATS_SERVERS}"
nats_instanceId: "${node.id}"
"""


def create_nats_executor_config(node):
    """创建默认的 NATS 配置"""

    try:
        collector_obj = Collector.objects.filter(
            name='NATS-Executor', node_operating_system=node.operating_system
        ).first()
        configuration = CollectorConfiguration.objects.create(
            name=f'nats_executor-{node.id}',
            collector=collector_obj,
            config_template=NATS_EXECUTOR_CONFIG,
            is_pre=True,
        )
        configuration.nodes.add(node)
    except Exception as e:
        logger.error(f"create node {node.id} NATS Executor default configuration failed {e}")