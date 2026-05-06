from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class MemcachedNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "memcached"
    plugin_name = "memcached_info"
