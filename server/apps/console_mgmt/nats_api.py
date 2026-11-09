import nats_client
from apps.console_mgmt.models import Notification
from apps.core.logger import opspilot_logger as logger
from apps.system_mgmt.models import App

MAX_MESSAGE_LENGTH = 2000

BUILTIN_APP_MODULES = frozenset(
    {
        "monitor",
        "cmdb",
        "node_mgmt",
        "job_mgmt",
        "alerts",
        "log",
        "opspilot",
        "system_mgmt",
        "console_mgmt",
        "mlops",
        "operation_analysis",
        "itsm",
    }
)


@nats_client.register
def create_notification(app, message, recipient_usernames=None, target_url="", event_key=None):
    """
    创建通知消息
    :param app: 应用模块名称
    :param message: 通知内容
    :param recipient_usernames: 接收用户名；空列表表示全员可见
    :param target_url: 站内通知跳转地址
    :param event_key: 幂等键，重复事件不重复落库
    :return: 创建结果
    """
    try:
        # 校验 app 白名单
        if app not in BUILTIN_APP_MODULES and not App.objects.filter(name=app).exists():
            logger.warning(f"通知创建被拒绝: 非法 app={app}")
            return {"result": False, "message": f"Invalid app module: {app}"}

        # 校验 message 长度
        if len(message) > MAX_MESSAGE_LENGTH:
            logger.warning(f"通知创建被拒绝: message 超长({len(message)}), app={app}")
            return {"result": False, "message": f"Message too long (max {MAX_MESSAGE_LENGTH} characters)"}

        if event_key and Notification.objects.filter(event_key=event_key).exists():
            return {"result": True, "duplicated": True}
        notification = Notification.objects.create(
            app_module=app,
            content=message,
            source=app,
            recipient_usernames=list(recipient_usernames or []),
            target_url=target_url or "",
            event_key=event_key,
        )
        logger.info(f"创建通知消息成功: app={app}, notification_id={notification.id}")
        return {"result": True}
    except Exception as e:
        logger.error(f"创建通知消息失败: app={app}, error={str(e)}")
        return {"result": False, "message": str(e)}
