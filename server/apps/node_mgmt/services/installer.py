import uuid

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import SidecarEnv
from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode, CollectorTaskNode, CollectorTask
from apps.node_mgmt.utils.installer import get_install_command
from apps.node_mgmt.utils.token_auth import generate_node_token


class InstallerService:

    @staticmethod
    def get_install_command(user, ip, os, package_name, cloud_region_id, organizations, node_name):
        """获取安装命令"""
        # 获取安装命令所需参数
        node_id = uuid.uuid4().hex
        sidecar_token = generate_node_token(node_id, ip, user)
        obj = SidecarEnv.objects.filter(cloud_region=cloud_region_id, key=NodeConstants.SERVER_URL_KEY).first()
        server_url = obj.value if obj else "null"
        groups = ",".join([ str(i) for i in organizations])
        return get_install_command(os, package_name, cloud_region_id, sidecar_token, server_url, groups, node_name, node_id)

    @staticmethod
    def install_controller(cloud_region_id, work_node, package_version_id, nodes):
        """安装控制器"""
        task_obj = ControllerTask.objects.create(
            cloud_region_id=cloud_region_id,
            work_node=work_node,
            package_version_id=package_version_id,
            type="install",
            status="waiting",
        )
        creates = []
        aes_obj = AESCryptor()
        for node in nodes:
            creates.append(ControllerTaskNode(
                task_id=task_obj.id,
                ip=node["ip"],
                node_name=node["node_name"],
                os=node["os"],
                organizations=node["organizations"],
                port=node["port"],
                username=node["username"],
                password=aes_obj.encode(node["password"]),
                status="waiting",
            ))
        ControllerTaskNode.objects.bulk_create(creates, batch_size=100)
        return task_obj.id

    @staticmethod
    def uninstall_controller(cloud_region_id, work_node, nodes):
        """卸载控制器"""
        task_obj = ControllerTask.objects.create(
            cloud_region_id=cloud_region_id,
            work_node=work_node,
            type="uninstall",
            status="waiting",
        )
        creates = []
        aes_obj = AESCryptor()
        for node in nodes:
            creates.append(ControllerTaskNode(
                task_id=task_obj.id,
                ip=node["ip"],
                os=node["os"],
                port=node["port"],
                username=node["username"],
                password=aes_obj.encode(node["password"]),
                status="waiting",
            ))
        ControllerTaskNode.objects.bulk_create(creates, batch_size=100)
        return task_obj.id

    @staticmethod
    def install_controller_nodes(task_id):
        """获取控制器安装节点信息"""
        task_nodes = ControllerTaskNode.objects.filter(task_id=task_id)
        result = []
        for task_node in task_nodes:
            result.append(dict(
                ip=task_node.ip,
                os=task_node.os,
                organizations=task_node.organizations,
                port=task_node.port,
                status=task_node.status,
                result=task_node.result,
            ))
        return result

    @staticmethod
    def install_collector(collector_package, nodes):
        """安装采集器"""
        task_obj = CollectorTask.objects.create(
            type="install",
            status="waiting",
            package_version_id=collector_package,
        )
        creates = []
        for node_id in nodes:
            creates.append(CollectorTaskNode(
                task_id=task_obj.id,
                node_id=node_id,
                status="waiting",
            ))
        CollectorTaskNode.objects.bulk_create(creates, batch_size=100)
        return task_obj.id

    @staticmethod
    def install_collector_nodes(task_id):
        """获取采集器安装节点信息"""
        task_nodes = CollectorTaskNode.objects.filter(task_id=task_id).select_related("node")
        result = []
        for task_node in task_nodes:
            result.append(dict(
                node_id=task_node.node_id,
                status=task_node.status,
                result=task_node.result,
                ip=task_node.node.ip,
                os=task_node.node.operating_system,
                # organizations=task_node.node.nodeorganization_set.values_list("organization", flat=True),
            ))
        return result
