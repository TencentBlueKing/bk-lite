from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class WebsphereNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "websphere"
    plugin_name = "websphere_info"
