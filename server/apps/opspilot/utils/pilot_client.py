from apps.core.logger import logger
from apps.opspilot.models import Bot
from apps.opspilot.utils.kubernetes_client import KubernetesClient


class PilotClient(object):
    def __init__(self):
        """
        :param namespace: 操作的目标NameSpace
        :param kube_config_file: 目标KubeConfig，不填写则获取默认配置文件路径
        """

        self.kube_client = KubernetesClient()

    def start_pilot(self, bot: Bot):
        logger.info(f"启动Pilot: {bot.id}")
        try:
            result = self.kube_client.start_pilot(bot)
        except Exception as e:
            logger.exception(f"启动Pilot失败: {e}")
            raise Exception("无法连接到Pilot服务，请检查服务是否正常运行。")
        return result

    def stop_pilot(self, bot_id):
        try:
            result = self.kube_client.stop_pilot(bot_id)
        except Exception as e:
            logger.exception(f"启动Pilot失败: {e}")
            raise Exception("无法连接到Pilot服务，请检查服务是否正常运行。")
        return result

    def list_pilot(self):
        result = self.kube_client.list_pilot()
        return result
