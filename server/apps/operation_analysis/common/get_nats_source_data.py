# -- coding: utf-8 --
# @File: get_nats_source_data.py
# @Time: 2025/7/22 18:24
# @Author: windyzhao
from apps.operation_analysis.nats.nats_client import DefaultNastClient
from apps.core.logger import operation_analysis_logger as logger
from rest_framework.exceptions import ValidationError


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

    def _get_target_namespace(self):
        """
        从 params 中取出 namespace_id（同时移除，避免透传给 NATS 接口），
        返回本次需要查询的单个 namespace 对象。
        若未指定则返回第一个可用 namespace。
        """
        namespace_id = self.params.pop("namespace_id", None)
        if namespace_id is not None:
            try:
                namespace_id = int(namespace_id)
            except (TypeError, ValueError):
                raise ValidationError("namespace_id 非法")

        if namespace_id is not None:
            for ns in self.namespace_list:
                if ns.id == namespace_id:
                    return ns
            raise ValidationError("所选命名空间未绑定到当前数据源")

        # 未指定或未匹配到，返回第一个
        return self.namespace_list[0] if self.namespace_list else None

    def get_data(self):
        """
        获取单个 namespace 的 NATS 数据源数据，直接返回裸数据。
        """
        namespace = self._get_target_namespace()
        if namespace is None:
            raise ValidationError("当前数据源没有可用命名空间")

        server_url = self.namespace_server_map.get(namespace.id)
        if not server_url:
            raise ValidationError("命名空间连接配置不完整")

        nats_namespace = getattr(namespace, "namespace", "bk_lite")
        nats_client = self._get_client(server=server_url, namespace=nats_namespace)
        try:
            if hasattr(nats_client, "DEFAULT_NATS"):
                fun = getattr(nats_client, "get_customization_nast_data", None)
            else:
                fun = getattr(nats_client, self.path, None)
            if fun is None:
                raise RuntimeError(f"NamePaces({self.namespace}) Module not found func({self.path})!")

            return_data = fun(**self.params)
            return return_data.get("data", [])
        except Exception as e:  # noqa
            import traceback

            logger.error("==获取NATS数据源数据失败==: namespace={} error={}".format(namespace.name, traceback.format_exc()))
            raise RuntimeError("获取NATS数据源数据失败") from e
