from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class TuxedoNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "tuxedo"
    plugin_name = "tuxedo_info"
