from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode, CollectorTaskNode, CollectorTask
from apps.node_mgmt.utils.installer import get_install_command


class InstallerService:

    @staticmethod
    def get_install_command(os, package_name, cloud_region_id):
        """获取安装命令"""
        return get_install_command(os, package_name, cloud_region_id)

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
        for node in nodes:
            creates.append(ControllerTaskNode(
                task_id=task_obj.id,
                ip=node["ip"],
                os=node["os"],
                organizations=node["organizations"],
                port=node["port"],
                username=node["username"],
                password=node["password"],
                result={"status": "waiting", "message": ""},
            ))
        ControllerTaskNode.objects.bulk_create(creates, batch_size=100)
        return task_obj.id

    @staticmethod
    def uninstall_controller(cloud_region_id, work_node, nodes):
        """安装控制器"""
        task_obj = ControllerTask.objects.create(
            cloud_region_id=cloud_region_id,
            work_node=work_node,
            type="uninstall",
            status="waiting",
        )
        creates = []
        for node in nodes:
            creates.append(ControllerTaskNode(
                task_id=task_obj.id,
                ip=node["ip"],
                os=node["os"],
                port=node["port"],
                username=node["username"],
                password=node["password"],
                result={"status": "waiting", "message": ""},
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
                result={"status": "waiting", "message": ""},
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
