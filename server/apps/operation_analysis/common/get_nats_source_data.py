# -- coding: utf-8 --
# @File: get_nats_source_data.py
# @Time: 2025/7/22 18:24
# @Author: windyzhao
from apps.operation_analysis.nats.nats_client import DefaultNastClient
from apps.core.logger import operation_analysis_logger as logger


class GetNatsData:
    """
    获取NATS数据源数据
    """

    def __init__(self, namespace: str, path: str, namespace_list: list, params: dict = None, request=None):
        self.request = request
        self.path = path
        self.params = params if params is not None else {}
        self.update_request_params()
        self.namespace = namespace
        self.namespace_list = namespace_list
        self.namespace_server_map = self.set_namespace_servers()

    @property
    def default_nats_client(self):
        return DefaultNastClient

    @property
    def default_namespace_name(self):
        return "default"

    @property
    def user_param_key(self):
        return "user_info"

    def update_request_params(self):
        """
        更新请求参数 带上当前请求的用户和组织信息
        :return:
        """
        username = self.request.user.username
        team = int(self.request.COOKIES.get("current_team"))
        self.params[self.user_param_key] = {
            "team": team,
            "user": username
        }

    def set_namespace_servers(self):
        """
        构建NATS服务器连接URL
        根据enable_tls字段决定使用nats://或tls://协议
        """
        result = {}
        for namespace in self.namespace_list:
            # 根据enable_tls字段确定协议
            protocol = "tls" if namespace.enable_tls else "nats"

            # 构建完整的服务器URL
            if ':' not in namespace.domain:
                # 域名不包含端口,使用默认端口4222
                server_url = f"{protocol}://{namespace.account}:{namespace.decrypt_password}@{namespace.domain}:4222"
            else:
                # 域名已包含端口,直接使用
                server_url = f"{protocol}://{namespace.account}:{namespace.decrypt_password}@{namespace.domain}"

            result[namespace.id] = server_url
        return result

    def _get_client(self, server, namespace):
        client = self.default_nats_client(server=server, func_name=self.path, namespace=namespace)

        return client

    def get_data(self) -> dict:
        """
        获取NATS数据源数据
        :return: 数据内容
        TODO 如果速度过慢，可以考虑使用多线程或异步方式来并发获取数据
        """
        result = {}
        for namespace in self.namespace_list:
            server_url = self.namespace_server_map[namespace.id]
            nats_namespace = getattr(namespace, 'namespace', 'bk_lite')
            nats_client = self._get_client(server=server_url, namespace=nats_namespace)
            try:
                if hasattr(nats_client, "DEFAULT_NATS"):
                    fun = getattr(nats_client, "get_customization_nast_data", None)
                else:
                    fun = getattr(nats_client, self.path, None)
                if fun is None:
                    raise RuntimeError(f"NamePaces({self.namespace}) Module not found func({self.path})!")

                return_data = fun(**self.params)
                result[namespace.name] = return_data.get("data", [])
            except Exception as e:  # noqa
                result[namespace.name] = []
                import traceback
                logger.error(
                    "==获取NATS数据源数据失败==: namespace={} error={}".format(namespace.name, traceback.format_exc()))

        return result
