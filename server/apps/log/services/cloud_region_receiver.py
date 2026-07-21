from urllib.parse import urlsplit


class CloudRegionReceiverService:
    """解析日志接收端对上报设备可见的云区域地址。"""

    @staticmethod
    def resolve(node_mgmt, cloud_region_id, organization_ids=None) -> str:
        if organization_ids == []:
            return ""

        proxy_address = node_mgmt.get_cloud_region_proxy_address(cloud_region_id, organization_ids)
        if proxy_address:
            return proxy_address

        if organization_ids:
            node_data = node_mgmt.node_list(
                {
                    "cloud_region_id": cloud_region_id,
                    "organization_ids": organization_ids,
                    "page": 1,
                    "page_size": 1,
                    "is_container": True,
                }
            )
            if not isinstance(node_data, dict) or not node_data.get("nodes"):
                return ""

        env_config = node_mgmt.get_cloud_region_envconfig(cloud_region_id)
        if not isinstance(env_config, dict):
            return ""

        node_server_url = env_config.get("NODE_SERVER_URL")
        if not node_server_url:
            return ""

        try:
            parsed_url = urlsplit(node_server_url)
        except ValueError:
            return ""
        if not parsed_url.scheme or not parsed_url.hostname:
            return ""
        return parsed_url.hostname
