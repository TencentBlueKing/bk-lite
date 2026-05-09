from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class SquidNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "squid"
    plugin_name = "squid_info"
