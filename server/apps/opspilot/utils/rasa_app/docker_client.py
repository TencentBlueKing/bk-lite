from typing import Any, Dict, List

import docker
from django.conf import settings

from apps.core.logger import opspilot_logger as logger


class DockerClient(object):
    def __init__(self):
        """
        初始化Docker客户端
        Docker socket默认挂载到容器中，使用默认的客户端配置
        """
        try:
            self.client = docker.from_env()
            self.api_client = docker.APIClient()
            logger.info("Docker客户端初始化成功")
        except Exception as e:
            logger.error(f"Docker客户端初始化失败: {e}")
            raise Exception("无法连接到Docker服务，请检查Docker是否正常运行。")

    def start_lobe_chat(self, bot) -> bool:
        """
        启动LobeChat容器
        :param bot: Bot模型实例
        :return: 是否成功启动
        """
        container_name = f"lobe-chat-{bot.id}"
        skill_list = [f"+{i.name}" for i in bot.llm_skills.all()]

        # 构建环境变量
        environment = {
            "TZ": "Asia/Shanghai",
            "OPENAI_API_KEY": bot.api_token,  # 使用bot的api_token作为OpenAI API Key
            "OPENAI_PROXY_URL": settings.MUNCHKIN_BASE_URL.strip("/") + "/bot_mgmt/lobe_chat/v1/",  # 代理URL配置
            "BK_LITE_APP_ID": bot.id,
            "OPENAI_MODEL_LIST": ",".join(skill_list),
            "NEXT_PUBLIC_ENABLE_NEXT_AUTH": "1",
            "NEXT_AUTH_SECRET": bot.api_token,
            "NEXT_AUTH_SSO_PROVIDERS": "bklite",
            "AUTH_BKLITE_API_URL": settings.LOGIN_URL,
        }

        # 端口映射配置 - 修改为3000端口
        ports = {}  # 默认随机分配主机端口
        if bot.enable_node_port and bot.node_port:
            ports["3210/tcp"] = bot.node_port

        # 配置标签
        labels = {"app": "lobe-chat", "bot-id": str(bot.id)}

        # 如果存在bot_domain，添加Traefik相关标签
        if bot.bot_domain:
            labels.update(
                {
                    "traefik.enable": "true",
                    f"traefik.http.routers.lobe-chat-{bot.id}.rule": f"Host(`{bot.bot_domain}`)",
                    f"traefik.http.routers.lobe-chat-{bot.id}.entrypoints": "https",
                    f"traefik.http.routers.lobe-chat-{bot.id}.tls": "true",
                    f"traefik.http.services.lobe-chat-{bot.id}.loadbalancer.server.port": "3210",
                }
            )

        try:
            # 验证必要的配置参数
            if not bot.api_token:
                raise ValueError("Bot API token 不能为空")

            # 检查是否已存在同名容器，如存在则先移除
            self._remove_container_if_exists(container_name)

            # 创建并启动容器 - 移除复杂的command，使用默认启动
            container = self.client.containers.run(
                image="bklite/lobe-chat:latest",
                name=container_name,
                detach=True,
                environment=environment,
                ports=ports,
                labels=labels,
                restart_policy={"Name": "always"},
                network=settings.CONVERSATION_DOCKER_NETWORK,
                # 移除command参数，使用镜像默认启动命令
            )
            logger.info(f"启动Pilot[{bot.id}]容器成功，容器ID: {container.id}")
            return True
        except Exception as e:
            logger.error(f"启动LobeChat[{bot.id}]容器失败: {e}")
            return False

    def start_pilot(self, bot) -> bool:
        """
        启动Pilot容器
        :param bot: Bot模型实例
        :return: 是否成功启动
        """
        container_name = f"pilot-{bot.id}"

        # 构建环境变量
        environment = {
            "TZ": "Asia/Shanghai",
            "RASA_TELEMETRY_ENABLED": "false",
            "MUNCHKIN_BOT_ID": str(bot.id),
            "MUNCHKIN_API_KEY": bot.api_token,
            "MUNCHKIN_BASE_URL": settings.MUNCHKIN_BASE_URL,
            "NATS_URL": settings.NATS_SERVERS,
            "NATS_NAMESPACE": settings.NATS_NAMESPACE,
            "ENABLE_SSL": "1" if bot.enable_ssl else "0",
            "BOT_DOMAIN": bot.bot_domain or "",
        }

        # 端口映射配置
        ports = {}
        if bot.enable_node_port and bot.node_port:
            ports["5005/tcp"] = bot.node_port

        # 配置标签
        labels = {"app": "pilot", "bot-id": str(bot.id)}

        # 配置extra_hosts
        # extra_hosts = {"rabbitmq-service": settings.CONVERSATION_MQ_HOST}

        # 如果存在bot_domain，添加Traefik相关标签
        if bot.bot_domain:
            labels.update(
                {
                    "traefik.enable": "true",
                    f"traefik.http.routers.pilot-{bot.id}.rule": f"Host(`{bot.bot_domain}`)",
                    f"traefik.http.routers.pilot-{bot.id}.entrypoints": "https",
                    f"traefik.http.routers.pilot-{bot.id}.tls": "true",
                    f"traefik.http.services.pilot-{bot.id}.loadbalancer.server.port": "5005",
                }
            )

        # 启动命令
        command = "/bin/sh -c 'mkdir -p data && python3 cli.py get_bot_config_data && supervisord -n'"

        try:
            # 检查是否已存在同名容器，如存在则先移除
            self._remove_container_if_exists(container_name)

            # 创建并启动容器
            container = self.client.containers.run(
                image="bklite/pilot:latest",
                name=container_name,
                detach=True,
                environment=environment,
                ports=ports,
                labels=labels,
                restart_policy={"Name": "always"},
                network=settings.CONVERSATION_DOCKER_NETWORK,
                command=command,
                # extra_hosts=extra_hosts,
            )

            logger.info(f"启动Pilot[{bot.id}]容器成功，容器ID: {container.id}")
            return True

        except Exception as e:
            logger.error(f"启动Pilot[{bot.id}]容器失败: {e}")
            return False

    def stop_lobe_chat(self, bot_id) -> bool:
        """
        停止并移除LobeChat容器
        :param bot_id: Bot ID
        :return: 是否成功停止
        """
        container_name = f"lobe-chat-{bot_id}"
        try:
            return self._remove_container_if_exists(container_name)
        except Exception as e:
            logger.error(f"停止LobeChat[{bot_id}]容器失败: {e}")
            return False

    def stop_pilot(self, bot_id) -> bool:
        """
        停止并移除Pilot容器
        :param bot_id: Bot ID
        :return: 是否成功停止
        """
        container_name = f"pilot-{bot_id}"
        try:
            return self._remove_container_if_exists(container_name)
        except Exception as e:
            logger.error(f"停止Pilot[{bot_id}]容器失败: {e}")
            return False

    def list_pilot(self) -> List[Dict[str, Any]]:
        """
        列出所有Pilot容器
        :return: 容器列表
        """
        try:
            containers = self.client.containers.list(all=True, filters={"label": "app=pilot"})
            container_list = [
                {
                    "name": container.name,
                    "status": container.status,
                    "id": container.id[:12],
                }
                for container in containers
            ]
            logger.info(f"共找到 {len(container_list)} 个Pilot容器")
            return container_list
        except Exception as e:
            logger.error(f"列出Pilot容器失败: {e}")
            return []

    def _remove_container_if_exists(self, container_name) -> bool:
        """
        如果容器存在则停止并删除
        :param container_name: 容器名称
        :return: 是否成功操作
        """
        try:
            try:
                container = self.client.containers.get(container_name)
                if container.status == "running":
                    container.stop(timeout=10)
                    logger.info(f"停止容器 {container_name} 成功")
                container.remove(force=True)
                logger.info(f"删除容器 {container_name} 成功")
                return True
            except docker.errors.NotFound:
                # 容器不存在，不需要操作
                return True
        except Exception as e:
            logger.error(f"移除容器 {container_name} 失败: {e}")
            return False
