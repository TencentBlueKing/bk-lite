from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class RocketmqNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "rocketmq"
    plugin_name = "rocketmq_info"
