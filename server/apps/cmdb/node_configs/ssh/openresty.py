from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class OpenrestyNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "openresty"
    plugin_name = "openresty_info"
