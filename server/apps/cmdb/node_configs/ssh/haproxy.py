from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class HaproxyNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "haproxy"
    plugin_name = "haproxy_info"
