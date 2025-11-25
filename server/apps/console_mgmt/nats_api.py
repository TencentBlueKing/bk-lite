import nats_client
from apps.console_mgmt.models import Notification
from apps.core.logger import opspilot_logger as logger


@nats_client.register
def create_notification(app, message):
    """
    创建通知消息
    :param app: 应用模块名称
    :param message: 通知内容
    :return: 创建结果
    """
    try:
        notification = Notification.objects.create(
            app_module=app,
            content=message,
        )
        logger.info(f"创建通知消息成功: app={app}, notification_id={notification.id}")
        return {"result": True}
    except Exception as e:
        logger.error(f"创建通知消息失败: app={app}, error={str(e)}")
        return {"result": False, "message": str(e)}
