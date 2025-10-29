import os
from typing import Any, Dict, List

import yaml
from django.conf import settings
from kubernetes import client, config

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.template_loader import core_template


class KubernetesClient(object):
    def __init__(self):
        """
        :param namespace: 操作的目标NameSpace
        """
        if settings.KUBE_CONFIG_FILE == "":
            config.load_incluster_config()
        else:
            config.load_kube_config(config_file=settings.KUBE_CONFIG_FILE)

        self.core_api = client.CoreV1Api()
        self.app_api = client.AppsV1Api()
        self.storage_api = client.StorageV1Api()
        self.custom_object_api = client.CustomObjectsApi()
        self.batch_api = client.BatchV1Api()
        self.traefik_resource_group = "traefik.io"

        self.argo_resource_group = "argoproj.io"
        self.argo_resource_version = "v1alpha1"
        self.namespace = settings.KUBE_NAMESPACE

    def start_lobe_chat(self, bot) -> bool:
        skill_list = [f"+{i.name}" for i in bot.llm_skills.all()]
        dynamic_dict = {
            "bot_id": bot.id,
            "replicas": bot.replica_count,
            "api_key": bot.api_token,
            "base_url": settings.MUNCHKIN_BASE_URL.strip("/") + "/bot_mgmt/lobe_chat/v1/",
            "enable_ssl": bot.enable_ssl,
            "bot_domain": bot.bot_domain or "",
            "enable_nodeport": bot.enable_node_port,
            "web_nodeport": bot.node_port,
            "bot_namespace": self.namespace,
            "model_list": ",".join(skill_list),
            "login_url": settings.LOGIN_URL,
        }
        try:
            logger.info(f"当前工作目录: {os.getcwd()}")
            logger.info("尝试加载模板: lobe/deployment.yml")
            deployment_template = core_template.get_template("lobe/deployment.yml")
            deployment = deployment_template.render(dynamic_dict)
            self.app_api.create_namespaced_deployment(namespace=self.namespace, body=yaml.safe_load(deployment))
            logger.info(f"启动LobeChat[{bot.id}]Pod成功")
        except Exception as e:
            logger.error(f"启动LobeChat[{bot.id}]Pod失败: {e}")

        try:
            svc_template = core_template.get_template("lobe/svc.yml")
            svc = svc_template.render(dynamic_dict)
            self.core_api.create_namespaced_service(namespace=self.namespace, body=yaml.safe_load(svc))
            logger.info(f"启动LobeChat[{bot.id}]Service成功")
        except Exception as e:
            logger.error(f"启动LobeChat[{bot.id}]Service失败: {e}")

        if bot.enable_bot_domain:
            # try:
            #     middleware_template = core_template.get_template("lobe/middleware.yml")
            #     middleware = middleware_template.render(dynamic_dict)
            #     self.custom_object_api.create_namespaced_custom_object(
            #         group=self.traefik_resource_group,
            #         version="v1alpha1",
            #         plural="middlewares",
            #         body=yaml.safe_load(middleware),
            #         namespace=self.namespace,
            #     )
            #     logger.info(f"启动LobeChat[{bot.id}]Middleware成功")
            # except Exception as e:
            #     logger.error(f"启动LobeChat[{bot.id}] Middleware失败: {e}")

            try:
                ingress_template = core_template.get_template("lobe/ingress.yml")
                ingress = ingress_template.render(dynamic_dict)
                self.custom_object_api.create_namespaced_custom_object(
                    group=self.traefik_resource_group,
                    version="v1alpha1",
                    plural="ingressroutes",
                    body=yaml.safe_load(ingress),
                    namespace=self.namespace,
                )
                logger.info(f"启动LobeChat[{bot.id}]Ingress成功")
            except Exception as e:
                logger.error(f"启动LobeChat[{bot.id}] Ingress失败: {e}")
        return True

    def start_pilot(self, bot) -> bool:
        dynamic_dict = {
            "bot_id": bot.id,
            "replicas": bot.replica_count,
            "api_key": bot.api_token,
            "base_url": settings.MUNCHKIN_BASE_URL,
            "nats_url": settings.NATS_SERVERS,
            "nats_namespace": settings.NATS_NAMESPACE,
            "enable_ssl": bot.enable_ssl,
            "bot_domain": bot.bot_domain or "",
            "enable_nodeport": bot.enable_node_port,
            "web_nodeport": bot.node_port,
            "bot_namespace": settings.KUBE_NAMESPACE,
        }
        try:
            logger.info(f"当前工作目录: {os.getcwd()}")
            logger.info("尝试加载模板: pilot/deployment.yml")
            deployment_template = core_template.get_template("pilot/deployment.yml")
            deployment = deployment_template.render(dynamic_dict)
            self.app_api.create_namespaced_deployment(namespace=settings.KUBE_NAMESPACE, body=yaml.safe_load(deployment))
            logger.info(f"启动Pilot[{bot.id}]Pod成功")
        except Exception as e:
            logger.error(f"启动Pilot[{bot.id}]Pod失败: {e}")

        try:
            svc_template = core_template.get_template("pilot/svc.yml")
            svc = svc_template.render(dynamic_dict)
            self.core_api.create_namespaced_service(namespace=settings.KUBE_NAMESPACE, body=yaml.safe_load(svc))
            logger.info(f"启动Pilot[{bot.id}]Service成功")
        except Exception as e:
            logger.error(f"启动Pilot[{bot.id}]Service失败: {e}")

        if bot.enable_bot_domain:
            try:
                middleware_template = core_template.get_template("pilot/middleware.yml")
                middleware = middleware_template.render(dynamic_dict)
                self.custom_object_api.create_namespaced_custom_object(
                    group=self.traefik_resource_group,
                    version="v1alpha1",
                    plural="middlewares",
                    body=yaml.safe_load(middleware),
                    namespace=settings.KUBE_NAMESPACE,
                )
                logger.info(f"启动Pilot[{bot.id}]Middleware成功")
            except Exception as e:
                logger.error(f"启动Pilot[{bot.id}] Middleware失败: {e}")

            try:
                ingress_template = core_template.get_template("pilot/ingress.yml")
                ingress = ingress_template.render(dynamic_dict)
                self.custom_object_api.create_namespaced_custom_object(
                    group=self.traefik_resource_group,
                    version="v1alpha1",
                    plural="ingressroutes",
                    body=yaml.safe_load(ingress),
                    namespace=settings.KUBE_NAMESPACE,
                )
                logger.info(f"启动Pilot[{bot.id}]Ingress成功")
            except Exception as e:
                logger.error(f"启动Pilot[{bot.id}] Ingress失败: {e}")
        return True

    def stop_pilot(self, bot_id) -> bool:
        try:
            self.app_api.delete_namespaced_deployment(name=f"pilot-{bot_id}", namespace=settings.KUBE_NAMESPACE)
            logger.info(f"停止Pilot[{bot_id}]Pod成功")
        except Exception as e:
            logger.error(f"停止Pilot[{bot_id}]Pod失败: {e}")

        try:
            self.core_api.delete_namespaced_service(name=f"pilot-{bot_id}-service", namespace=settings.KUBE_NAMESPACE)
            logger.info(f"停止Pilot[{bot_id}]Service成功")
        except Exception as e:
            logger.error(f"停止Pilot[{bot_id}]Service失败: {e}")

        try:
            self.custom_object_api.delete_namespaced_custom_object(
                group=self.traefik_resource_group,
                version="v1alpha1",
                plural="middlewares",
                namespace=settings.KUBE_NAMESPACE,
                name=f"pilot-{bot_id}",
            )
        except Exception as e:
            logger.error(f"停止Pilot[{bot_id}]Middleware失败: {e}")

        try:
            self.custom_object_api.delete_namespaced_custom_object(
                group=self.traefik_resource_group,
                version="v1alpha1",
                plural="ingressroutes",
                namespace=settings.KUBE_NAMESPACE,
                name=f"pilot-{bot_id}",
            )
        except Exception as e:
            logger.error(f"停止Pilot[{bot_id}]Ingress失败: {e}")

        return True

    def stop_lobe_chat(self, bot_id) -> bool:
        try:
            self.app_api.delete_namespaced_deployment(name=f"lobe-chat-{bot_id}", namespace=self.namespace)
            logger.info(f"停止LobeChat[{bot_id}]Pod成功")
        except Exception as e:
            logger.error(f"停止LobeChat[{bot_id}]Pod失败: {e}")

        try:
            self.core_api.delete_namespaced_service(name=f"lobe-chat-{bot_id}-service", namespace=self.namespace)
            logger.info(f"停止LobeChat[{bot_id}]Service成功")
        except Exception as e:
            logger.error(f"停止LobeChat[{bot_id}]Service失败: {e}")

        # try:
        #     self.custom_object_api.delete_namespaced_custom_object(
        #         group=self.traefik_resource_group,
        #         version="v1alpha1",
        #         plural="middlewares",
        #         namespace=self.namespace,
        #         name=f"lobe-chat-{bot_id}",
        #     )
        # except Exception as e:
        #     logger.error(f"停止LobeChat[{bot_id}]Middleware失败: {e}")

        try:
            self.custom_object_api.delete_namespaced_custom_object(
                group=self.traefik_resource_group,
                version="v1alpha1",
                plural="ingressroutes",
                namespace=self.namespace,
                name=f"lobe-chat-{bot_id}",
            )
        except Exception as e:
            logger.error(f"停止LobeChat[{bot_id}]Ingress失败: {e}")

        return True

    def list_pilot(self) -> List[Dict[str, Any]]:
        try:
            pods = self.core_api.list_namespaced_pod(namespace=settings.KUBE_NAMESPACE, label_selector="")
            pod_list = [
                dict(name=pod.metadata.name, status=pod.status.phase)
                for pod in pods.items
                if pod.metadata.name.startswith("lobe-chat-") or pod.metadata.name.startswith("pilot")
            ]
            logger.info(f"共找到 {len(pods.items)} 个Pod")
            return pod_list

        except Exception as e:
            logger.error(f"列出命名空间'{settings.KUBE_NAMESPACE}'中的Pod失败: {e}")
            return []
