from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class JbossNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "jboss"
    plugin_name = "jboss_info"
