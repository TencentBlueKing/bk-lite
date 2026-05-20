import re

from apps.cmdb.collection.constants import COLLECTION_METRICS
from apps.cmdb.collection.query_vm import Collection
from apps.cmdb.constants.infra import InfraConstants
from apps.cmdb.services.infra import InfraService
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger


_COLLECTOR_ID_RE = re.compile(InfraConstants.COLLECTOR_CLUSTER_ID_PATTERN)


def validate_collector_cluster_id(value: str) -> str:
    if not value:
        raise BaseAppException("collector_cluster_id is required")
    if not _COLLECTOR_ID_RE.match(value):
        raise BaseAppException(
            "Invalid collector_cluster_id: only letters, digits, underscore and hyphen are allowed"
        )
    return value


class K8sSetupService:
    """CMDB k8s 引导式接入：token / render / verify"""

    @staticmethod
    def generate_install_token(collector_cluster_id: str, cloud_region_id) -> dict:
        validate_collector_cluster_id(collector_cluster_id)
        token = InfraService.generate_install_token(collector_cluster_id, cloud_region_id)
        return {
            "token": token,
            "expire_seconds": InfraConstants.TOKEN_EXPIRE_TIME,
            "max_usage": InfraConstants.TOKEN_MAX_USAGE,
        }

    @staticmethod
    def generate_install_command(collector_cluster_id: str, cloud_region_id) -> dict:
        """
        后端生成安装命令，URL 直连 Django open_api（不走 Next.js 代理），
        与 Monitor 的 ManualCollectService.generate_install_command 保持一致。
        """
        validate_collector_cluster_id(collector_cluster_id)

        from apps.rpc.node_mgmt import NodeMgmt

        node_mgmt_rpc = NodeMgmt()
        env_vars = node_mgmt_rpc.get_cloud_region_envconfig(cloud_region_id)

        server_url = env_vars.get("NODE_SERVER_URL")
        if not server_url:
            raise BaseAppException(
                f"Missing NODE_SERVER_URL in cloud region {cloud_region_id}"
            )

        token = InfraService.generate_install_token(collector_cluster_id, cloud_region_id)
        api_url = f"{server_url.rstrip('/')}/api/v1/cmdb/open_api/k8s_setup/render/"

        install_command = (
            f"curl -sSLk -X POST -H 'Content-Type: application/json' "
            f"{api_url} -d '{{\"token\":\"{token}\"}}' | kubectl apply -f -"
        )
        return {
            "command": install_command,
            "token": token,
            "expire_seconds": InfraConstants.TOKEN_EXPIRE_TIME,
            "max_usage": InfraConstants.TOKEN_MAX_USAGE,
        }

    @staticmethod
    def render_yaml_by_token(token: str) -> dict:
        token_data = InfraService.validate_and_get_token_data(token)
        yaml_content = InfraService.render_config_from_cloud_region(
            cluster_name=token_data["cluster_name"],
            cloud_region_id=token_data["cloud_region_id"],
            config_type="resource",
        )
        return {
            "yaml": yaml_content,
            "remaining_usage": token_data.get("remaining_usage", 0),
        }

    @staticmethod
    def verify_collector_reporting(collector_cluster_id: str) -> dict:
        """
        探测 VictoriaMetrics 是否已收到该 collector_cluster_id 的 k8s 指标。
        采用一个轻量级 metric（kube_namespace_labels 或任一 namespace metric）查询。
        """
        validate_collector_cluster_id(collector_cluster_id)

        namespace_metrics = COLLECTION_METRICS.get("namespace") or []
        if not namespace_metrics:
            raise BaseAppException("No namespace metric configured for verification")

        probe_metric = namespace_metrics[0]
        sql = f'{probe_metric}{{instance_id="{collector_cluster_id}"}}'

        try:
            data = Collection().query(sql)
        except Exception as e:
            logger.warning(f"verify_collector_reporting query failed: {e}")
            return {"reporting": False, "error": str(e)}

        result = (data.get("data") or {}).get("result") or []
        return {"reporting": bool(result), "sample_count": len(result)}
