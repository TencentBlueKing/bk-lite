from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.database import DatabaseConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import SidecarEnv, Node
from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode, CollectorTaskNode, CollectorTask
from apps.node_mgmt.services.install_token import InstallTokenService


class InstallerService:

    @staticmethod
    def get_install_command(user, ip, node_id, os, package_id, cloud_region_id, organizations, node_name):
        """
        获取安装命令（生成包含临时 token 的 curl 命令）

        :param user: 用户名
        :param ip: 节点IP
        :param node_id: 节点ID
        :param os: 操作系统
        :param package_id: 安装包ID
        :param cloud_region_id: 云区域ID
        :param organizations: 组织列表
        :param node_name: 节点名称
        :return: curl 命令字符串
        """
        # 从云区域环境变量中获取服务器地址
        objs = SidecarEnv.objects.filter(cloud_region=cloud_region_id)
        server_url = None
        for obj in objs:
            if obj.key == NodeConstants.SERVER_URL_KEY:
                server_url = obj.value
                break

        if not server_url:
            raise BaseAppException(f"Missing NODE_SERVER_URL in cloud region {cloud_region_id}")

        # 生成限时令牌（30分钟有效，最多使用5次）
        token = InstallTokenService.generate_install_token(
            node_id=node_id,
            ip=ip,
            user=user,
            os=os,
            package_id=package_id,
            cloud_region_id=cloud_region_id,
            organizations=organizations,
            node_name=node_name
        )

        # 构造 render API URL（本地服务，用于验证 token 并调用 webhook）
        # 使用 GET 方式，token 作为 query 参数，便于直接通过浏览器或 curl 访问
        render_api_url = f"{server_url.rstrip('/')}/api/v1/node_mgmt/open_api/installer/render?token={token}"

        # 根据操作系统生成不同的安装命令（最简洁的形式）
        if os == NodeConstants.LINUX_OS:
            # Linux: 直接 curl 下载脚本并通过管道执行
            # 添加 -k 参数跳过 SSL 证书验证（针对自签名证书或内网环境）
            install_command = f"curl -sSLk {render_api_url} | sudo bash"
        elif os == NodeConstants.WINDOWS_OS:
            # Windows: 使用 PowerShell 的 iwr (Invoke-WebRequest 简写) 下载脚本并执行
            # -UseBasicParsing: 不依赖 IE，适合服务器环境
            # iex: Invoke-Expression 的简写
            install_command = f"iwr {render_api_url} -UseBasicParsing -SkipCertificateCheck | iex"
        else:
            raise BaseAppException(f"Unsupported operating system: {os}")

        return install_command

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
            # 加密密码（如果有）
            password = aes_obj.encode(node["password"]) if node.get("password") else ""
            # 加密私钥（如果有）
            private_key = aes_obj.encode(node["private_key"]) if node.get("private_key") else ""
            # 加密密码短语（如果有）
            passphrase = aes_obj.encode(node["passphrase"]) if node.get("passphrase") else ""
            
            creates.append(ControllerTaskNode(
                task_id=task_obj.id,
                ip=node["ip"],
                node_name=node["node_name"],
                os=node["os"],
                organizations=node["organizations"],
                port=node["port"],
                username=node["username"],
                password=password,
                private_key=private_key,
                passphrase=passphrase,
                status="waiting",
            ))
        ControllerTaskNode.objects.bulk_create(creates, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
        return task_obj.id

    @staticmethod
    # 获取手动安装节点状态
    def get_manual_install_status(nodes):
        """获取手动安装节点状态"""
        exists_id = Node.objects.filter(id__in=nodes).values("id")
        exists_id_set = set([item["id"] for item in exists_id])
        result = []
        for node_id in nodes:
            info = {"node_id":node_id, "status": ""}
            if node_id in exists_id_set:
                info["status"] = "installed"
                result.append(info)
            else:
                info["status"] = "waiting"
                result.append(info)
        return result

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
            # 加密密码（如果有）
            password = aes_obj.encode(node["password"]) if node.get("password") else ""
            # 加密私钥（如果有）
            private_key = aes_obj.encode(node["private_key"]) if node.get("private_key") else ""
            # 加密密码短语（如果有）
            passphrase = aes_obj.encode(node["passphrase"]) if node.get("passphrase") else ""
            
            creates.append(ControllerTaskNode(
                task_id=task_obj.id,
                ip=node["ip"],
                os=node["os"],
                port=node["port"],
                username=node["username"],
                password=password,
                private_key=private_key,
                passphrase=passphrase,
                status="waiting",
            ))
        ControllerTaskNode.objects.bulk_create(creates, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
        return task_obj.id

    @staticmethod
    def install_controller_nodes(task_id):
        """获取控制器安装节点信息"""
        task_nodes = ControllerTaskNode.objects.filter(task_id=task_id)
        result = []
        for task_node in task_nodes:
            result.append(dict(
                task_node_id=task_node.id,
                ip=task_node.ip,
                os=task_node.os,
                node_name=task_node.node_name,
                organizations=task_node.organizations,
                username=task_node.username,
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
        CollectorTaskNode.objects.bulk_create(creates, batch_size=DatabaseConstants.BULK_CREATE_BATCH_SIZE)
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
