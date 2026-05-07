from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class IisNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "iis"
    plugin_name = "iis_info"
