import requests

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.rpc.executor import Executor


# 获取安装命令
def get_install_command(os, package_name, cloud_region_id, sidecar_token, server_url, groups, node_name, node_id):
    """获取安装命令"""
    unzip_run_command = ControllerConstants.RUN_COMMAND.get(os)
    unzip_run_command = unzip_run_command.format(
        package_name=package_name,
        server_url=server_url,
        server_token=sidecar_token,
        cloud=cloud_region_id,
        group=groups,
        node_name=node_name,
        node_id=node_id,
    )
    return unzip_run_command


# 获取手动安装命令
def get_manual_install_command(os, package_id, cloud_region_id, sidecar_token, server_url, groups, node_name, node_id, webhook_url):
    """获取手动安装命令"""
    api_url = f"{webhook_url.rstrip('/')}/infra/kubernetes" if webhook_url else None

    if not api_url:
        raise BaseAppException("Webhook API URL is required")

    try:

        params = {
            "os": os,
            "api_token": sidecar_token,
            "server_url": server_url,
            "node_id": node_id,
            "zone_id": cloud_region_id,
            "group_id": groups,
            "file_url": "http://download.example.com/collector-windows.zip"
        }

        # 使用 requests 调用外部 API
        response = requests.post(
            api_url,
            json=params,
            headers={'Content-Type': 'application/json'},
            timeout=InfraConstants.REQUEST_TIMEOUT,
            verify=False  # 跳过 SSL 证书验证
        )

        # 检查响应状态
        if response.status_code != 200:
            raise BaseAppException(
                f"Infra API returned status {response.status_code}: {response.text}"
            )

        # 解析响应（假设返回的是 {"yaml": "..."} 格式）
        response_data = response.json()
        yaml_content = response_data.get('yaml')

        if not yaml_content:
            raise BaseAppException("Invalid response from infra API: missing 'yaml' field")

        return yaml_content

    except requests.Timeout as e:
        raise BaseAppException(f"Infra API request timeout: {str(e)}")
    except requests.RequestException as e:
        raise BaseAppException(f"Infra API request failed: {str(e)}")
    except ValueError as e:
        raise BaseAppException(f"Failed to parse response from infra API: {str(e)}")
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        raise BaseAppException(f"Failed to render config: {str(e)} | Detail: {error_detail}")

    manual_install_command = ControllerConstants.MANUAL_INSTALL_COMMAND.get(os)
    manual_install_command = manual_install_command.format(
        package_id=package_id,
        server_url=server_url,
        server_token=sidecar_token,
        cloud=cloud_region_id,
        group=groups,
        node_name=node_name,
        node_id=node_id,
    )
    return manual_install_command


# 获取卸载命令
def get_uninstall_command(os):
    """获取卸载命令"""
    uninstall_command = ControllerConstants.UNINSTALL_COMMAND.get(os)
    return uninstall_command


# 执行本地命令
def exec_command_to_local(instance_id, command):
    exe_obj = Executor(instance_id)
    result = exe_obj.execute_local(command, timeout=600)
    return result


# 执行远程命令
def exec_command_to_remote(instance_id, ip, username, password, command, port=22):
    exe_obj = Executor(instance_id)
    result = exe_obj.execute_ssh(command, ip, username, password=password, timeout=600, port=port)
    return result


# 文件下发到本地
def download_to_local(instance_id, bucket_name, file_key, file_name, target_path):
    exe_obj = Executor(instance_id)
    result = exe_obj.download_to_local(bucket_name, file_key, file_name, target_path, timeout=600)
    return result


# 文件下发到远程
def download_to_remote(instance_id, bucket_name, file_key, file_name, target_path, host, username, password, port=22):
    exe_obj = Executor(instance_id)
    result = exe_obj.download_to_remote(bucket_name, file_key, file_name, target_path, host, username, password, timeout=600, port=port)
    return result


# 本机文件下发到远程
def transfer_file_to_remote(instance_id, local_path, remote_path, host, username, password, port=22):
    exe_obj = Executor(instance_id)
    result = exe_obj.transfer_file_to_remote(local_path, remote_path, host, username, password, timeout=600, port=port)
    return result


# 解压文件
def unzip_file(instance_id, file_path, target_path):
    exe_obj = Executor(instance_id)
    result = exe_obj.unzip_local(file_path, target_path, timeout=600)
    return result
