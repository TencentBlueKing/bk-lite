from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class CephNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "ceph"
    plugin_name = "ceph_info"
