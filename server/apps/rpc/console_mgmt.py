from apps.rpc.base import AppClient, RpcClient


class ConsoleMgmt:
    def __init__(self, is_local_client=False):
        self.client = AppClient("apps.console_mgmt.nats_api") if is_local_client else RpcClient()

    def create_notification(self, app, message, recipient_usernames=None, target_url="", event_key=None):
        """
        创建通知消息
        :param app: 应用模块名称
        :param message: 通知内容
        :param recipient_usernames: 接收用户名，空列表表示全员
        :param target_url: 点击通知后的跳转地址
        :param event_key: 幂等键
        :return: 创建结果
        """
        return_data = self.client.run(
            "create_notification",
            app=app,
            message=message,
            recipient_usernames=recipient_usernames,
            target_url=target_url,
            event_key=event_key,
        )
        return return_data
