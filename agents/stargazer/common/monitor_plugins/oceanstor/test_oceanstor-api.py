import json
import time
import traceback

import requests
from urllib3.exceptions import InsecureRequestWarning

# 禁用HTTPS证书校验警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# 初始化日志数据存储
api_logs = []
session = requests.Session()


def monkey_patch_requests():
    """对 requests 库进行猴子补丁，记录请求和响应"""
    old_request = requests.Session.request

    def new_request(session, method, url, **kwargs):
        request_data = {
            "method": method,
            "url": url,
            "headers": dict(kwargs.get("headers", {}) or {}),
            "params": dict(kwargs.get("params", {}) or {}),
            "data": kwargs.get("data", ""),
            "json": kwargs.get("json", ""),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        }
        error = None
        try:
            # 添加 verify=False 以豁免证书校验
            kwargs["verify"] = False
            response = old_request(session, method, url, **kwargs)
            result = response.content.decode()
            response_data = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "json_data": json.loads(result) if "{" in result else result,
            }
        except Exception as e:
            response_data = {
                "exception": repr(e),
                "traceback": traceback.format_exc(),
            }
            response = None
            error = e

        with open("test_oceanstor.txt", "a", encoding="utf-8") as f:
            f.write(json.dumps({"request": request_data, "response": response_data}, indent=4, ensure_ascii=False))
            f.write("\n" + "-" * 80 + "\n")

        if error:
            raise error
        return response

    requests.Session.request = new_request


def test_login(base_url, credentials):
    """测试登录接口"""
    url = f"{base_url}/deviceManager/rest/xxxxx/sessions"
    data = {"username": credentials["username"], "password": credentials["password"], "scope": "0"}
    response = session.post(url, json=data)
    if response.status_code == 200:
        data = response.json().get("data", {})
        token = data.get("iBaseToken")
        device_id = data.get("deviceid")
        if token:
            session.headers.update({"iBaseToken": token, "Content-Type": "application/json"})
        return device_id
    return None


def test_get_drive_config(base_url, device_id):
    """测试获取磁盘配置"""
    url = f"{base_url}/deviceManager/rest/{device_id}/disk"
    return session.get(url)


def test_get_volume_config(base_url, device_id):
    """测试获取卷配置"""
    url = f"{base_url}/deviceManager/rest/{device_id}/lun"
    return session.get(url)


def test_get_pool_config(base_url, device_id):
    """测试获取存储池配置"""
    url = f"{base_url}/deviceManager/rest/{device_id}/storagepool"
    return session.get(url)


def test_get_performance_data(base_url, device_id, obj_type, obj_id):
    """测试获取性能数据"""
    url = f"{base_url}/deviceManager/rest/{device_id}/performace_statistic/cur_statistic_data"
    data = {
        "CMO_STATISTIC_UUID": f"{obj_type}:{obj_id}",
        "CMO_STATISTIC_DATA_ID_LIST": ",".join(["22", "25", "28", "370", "23", "26", "384", "385"]),  # IO速率相关  # 读写延迟相关
    }
    return session.get(url, json=data)


def test_logout(base_url, device_id):
    """测试登出接口"""
    url = f"{base_url}/deviceManager/rest/{device_id}/sessions"
    return session.delete(url)


def main(base_url, credentials):
    """主测试流程"""
    print("Starting OceanStor API testing...")

    # 确保会话豁免证书校验
    session.verify = False

    # 测试登录
    print("\nTesting login API...")
    device_id = test_login(base_url, credentials)
    if not device_id:
        print("Login failed. Cannot proceed with API testing.")
        return

    try:
        # 测试获取存储池配置和性能数据
        print("\nTesting storage pools API...")
        pools_response = test_get_pool_config(base_url, device_id)
        if pools_response and pools_response.status_code == 200:
            pools = pools_response.json().get("data", [])
            for pool in pools:
                pool_id = pool.get("ID")
                if pool_id:
                    print(f"Testing pool performance data for {pool_id}...")
                    test_get_performance_data(base_url, device_id, "216", pool_id)

        # 测试获取磁盘配置和性能数据
        print("\nTesting drives API...")
        drives_response = test_get_drive_config(base_url, device_id)
        if drives_response and drives_response.status_code == 200:
            drives = drives_response.json().get("data", [])
            for drive in drives:
                drive_id = drive.get("ID")
                if drive_id:
                    print(f"Testing drive performance data for {drive_id}...")
                    test_get_performance_data(base_url, device_id, "10", drive_id)

        # 测试获取卷配置和性能数据
        print("\nTesting volumes API...")
        volumes_response = test_get_volume_config(base_url, device_id)
        if volumes_response and volumes_response.status_code == 200:
            volumes = volumes_response.json().get("data", [])
            for volume in volumes:
                volume_id = volume.get("ID")
                if volume_id:
                    print(f"Testing volume performance data for {volume_id}...")
                    test_get_performance_data(base_url, device_id, "11", volume_id)

    finally:
        # 测试登出
        print("\nTesting logout API...")
        test_logout(base_url, device_id)

    # 保存测试日志
    print("\nOceanStor API testing completed.")


if __name__ == "__main__":
    # 配置信息
    monkey_patch_requests()
    BASE_URL = "https://oceanstor-server"  # 替换为实际的OceanStor服务器地址
    CREDENTIALS = {"username": "admin", "password": "password"}  # 替换为实际的密码

    # 执行测试
    main(BASE_URL, CREDENTIALS)
