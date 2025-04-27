from apps.node_mgmt.constants import UNZIP_RUN_COMMAND, UNINSTALL_COMMAND, NODE_SERVER_URL_KEY
from apps.node_mgmt.models import SidecarEnv
from apps.node_mgmt.utils.token_auth import generate_token
from apps.rpc.executor import Executor


# 获取安装命令
def get_install_command(os, package_name, cloud_region_id):
    """获取安装命令"""
    unzip_run_command = UNZIP_RUN_COMMAND.get(os)
    sidecar_token = generate_token({"username": "admin"})
    obj = SidecarEnv.objects.filter(cloud_region=cloud_region_id, key=NODE_SERVER_URL_KEY).first()
    server_url = obj.value if obj else "null"
    unzip_run_command = unzip_run_command.format(package_name=package_name, server_url=server_url,
                                                 server_token=sidecar_token)
    return unzip_run_command


# 获取卸载命令
def get_uninstall_command(os):
    """获取卸载命令"""
    uninstall_command = UNINSTALL_COMMAND.get(os)
    return uninstall_command


# 执行本地命令
def exec_command_to_local(instance_id, command):
    exe_obj = Executor(instance_id)
    result = exe_obj.execute_local(command, timeout=600)
    return result


# 执行远程命令
def exec_command_to_remote(instance_id, ip, username, password, command):
    exe_obj = Executor(instance_id)
    result = exe_obj.execute_ssh(command, ip, username, password=password, timeout=600)
    return result


# 文件下发到本地
def download_to_local(instance_id, bucket_name, file_key, file_name, target_path):
    exe_obj = Executor(instance_id)
    result = exe_obj.download_to_local(bucket_name, file_key, file_name, target_path, timeout=600)
    return result


# 文件下发到远程
def download_to_remote(instance_id, bucket_name, file_key, file_name, target_path, host, username, password):
    exe_obj = Executor(instance_id)
    result = exe_obj.download_to_remote(bucket_name, file_key, file_name, target_path, host, username, password, timeout=600)
    return result
