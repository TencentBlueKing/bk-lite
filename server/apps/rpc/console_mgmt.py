from apps.rpc.base import AppClient, RpcClient


class ConsoleMgmt:
    def __init__(self, is_local_client=False):
        self.client = AppClient("apps.console_mgmt.nats_api") if is_local_client else RpcClient()

    def create_notification(self, app, message, source="unknown"):
        """
        创建通知消息
        :param app: 应用模块名称
        :param message: 通知内容
        :param source: 调用来源标识
        :return: 创建结果
        """
        return_data = self.client.run("create_notification", app=app, message=message, source=source)
        return return_data
