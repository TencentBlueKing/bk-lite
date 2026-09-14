from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class MinioNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "minio"
    plugin_name = "minio_info"
