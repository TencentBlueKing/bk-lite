import nats_client
from apps.console_mgmt.models import Notification
from apps.core.logger import opspilot_logger as logger
from apps.system_mgmt.models import App

MAX_MESSAGE_LENGTH = 2000

BUILTIN_APP_MODULES = frozenset({
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
})


@nats_client.register
def create_notification(app, message):
    """
    创建通知消息
    :param app: 应用模块名称
    :param message: 通知内容
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

        notification = Notification.objects.create(
            app_module=app,
            content=message,
            source=app,
        )
        logger.info(f"创建通知消息成功: app={app}, notification_id={notification.id}")
        return {"result": True}
    except Exception as e:
        logger.error(f"创建通知消息失败: app={app}, error={str(e)}")
        return {"result": False, "message": str(e)}
