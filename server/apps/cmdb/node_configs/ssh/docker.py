from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class DockerNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "docker"
    plugin_name = "docker_info"
