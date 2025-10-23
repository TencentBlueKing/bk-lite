# -- coding: utf-8 --
# @File: get_nats_source_data.py
# @Time: 2025/7/22 18:24
# @Author: windyzhao
from apps.operation_analysis.nats import DefaultNastClient
from apps.rpc.alerts import AlertOperationAnaRpc
from apps.rpc.monitor import MonitorOperationAnaRpc
from apps.rpc.log import LogOperationAnaRpc
from apps.core.logger import operation_analysis_logger as logger


class GetNatsData:
    """
    获取NATS数据源数据
    """

    def __init__(self, namespace: str, path: str, namespace_list: list, params: dict = {}, request=None):
        self.request = request
        self.path = path
        self.params = params or {}
        self.update_request_params()
        self.namespace = namespace
        self.namespace_list = namespace_list
        self.namespace_server_map = self.set_namespace_servers()
        self.namespace_map = self.set_namespace_map()

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
        result = {}
        for namespace in self.namespace_list:
            if ':' not in namespace.domain:
                server_url = f"nats://{namespace.account}:{namespace.decrypt_password}@{namespace.domain}:4222"
            else:
                server_url = f"nats://{namespace.account}:{namespace.decrypt_password}@{namespace.domain}"
            result[namespace.id] = server_url
        return result

    @staticmethod
    def set_namespace_map():
        result = {"alert": AlertOperationAnaRpc, "monitor": MonitorOperationAnaRpc, "log": LogOperationAnaRpc}
        return result

    def _get_client(self, server):
        if self.namespace not in self.namespace_map.keys():
            logger.info("==NATS命名空间未配置，使用默认命名空间==: namespace={}".format(self.namespace))
            client = self.default_nats_client(server=server, func_name=self.path)
        else:
            client = self.namespace_map[self.namespace](server=server)

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
            nats_client = self._get_client(server=server_url)
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
