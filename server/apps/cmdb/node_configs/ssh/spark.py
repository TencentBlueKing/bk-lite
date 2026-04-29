from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class SparkNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "spark"
    plugin_name = "spark_info"
