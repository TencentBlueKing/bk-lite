import json
import os
import time

import requests

# 初始化日志数据存储
api_logs = []
session = requests.Session()


def save_logs_to_json(output_dir, output_file, data):
    """保存API测试日志到JSON文件"""
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_file)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"API logs have been saved to {output_path}")


def log_api_call(func):
    """装饰器：记录API调用日志"""

    def wrapper(*args, **kwargs):
        log_entry = {
            "timestamp": int(time.time() * 1000),
            "endpoint_name": func.__name__,
            "url": kwargs.get("url", ""),
            "method": kwargs.get("method", "GET"),
        }
        try:
            result = func(*args, **kwargs)
            log_entry["status_code"] = result.status_code if isinstance(result, requests.Response) else None
            log_entry["response_data"] = result.json() if isinstance(result, requests.Response) else result
            return result
        except requests.RequestException as e:
            log_entry["status_code"] = None
            log_entry["error"] = str(e)
            return None
        finally:
            api_logs.append(log_entry)

    return wrapper


@log_api_call
def test_login(base_url, credentials):
    """测试登录接口"""
    url = f"{base_url}/api/v2/aa/sessions"
    data = {
        "user_name": credentials["username"],
        "password": credentials["password"],
        "scope": "0",
        "isEncrypt": "false",
    }
    response = session.post(url, json=data, verify=False)
    if response.status_code == 200:
        data = response.json().get("data", {})
        token = data.get("x_auth_token")
        if token:
            session.headers.update({"X-Auth-Token": token, "Content-Type": "application/json"})
    return response


@log_api_call
def test_get_pool_config(base_url):
    """测试获取存储池配置"""
    url = f"{base_url}/api/v2/data_service/storagepool"
    return session.get(url, verify=False)


@log_api_call
def test_get_disk_pool_info(base_url, pool_ids):
    """测试获取磁盘池信息"""
    url = f"{base_url}/dsware/service/cluster/diskpool/queryNodeDiskInfo"
    params = {"diskPoolId": ",".join(pool_ids)}
    return session.get(url, params=params, verify=False)


@log_api_call
def test_get_performance_data(base_url, indicators, start_time=None, end_time=None):
    """测试获取性能数据"""
    url = f"{base_url}/api/v2/pms/performance_data"
    if not start_time:
        start_time = int(time.time() - 600)  # 默认10分钟前
    if not end_time:
        end_time = int(time.time())

    data = {
        "begin_time": start_time,
        "end_time": end_time,
        "objects": [{"object_type": 10, "ids": ["*"], "indicators": indicators}],
    }
    return session.post(url, json=data, verify=False)


def main(base_url, credentials, output_dir, output_file):
    """主测试流程"""
    print("Starting OceanStor Pacific NAS API testing...")

    # 测试登录
    print("\nTesting login API...")
    login_response = test_login(base_url, credentials)
    if not login_response or login_response.status_code != 200:
        print("Login failed. Cannot proceed with API testing.")
        save_logs_to_json(output_dir, output_file, api_logs)
        return

    try:
        # 测试获取存储池配置
        print("\nTesting storage pool configuration API...")
        pools_response = test_get_pool_config(base_url)
        if pools_response and pools_response.status_code == 200:
            pools = pools_response.json().get("storagePools", [])
            pool_ids = [pool.get("storagePoolId") for pool in pools if pool.get("storagePoolId")]

            if pool_ids:
                # 测试获取磁盘池信息
                print("\nTesting disk pool info API...")
                test_get_disk_pool_info(base_url, pool_ids)

        # 测试性能数据指标
        print("\nTesting performance data API...")
        test_indicators = ["123", "124", "25", "28", "22", "428", "430", "432", "24", "27", "68", "69"]
        perf_response = test_get_performance_data(base_url, test_indicators)
        if perf_response and perf_response.status_code == 200:
            print("Performance data API test successful")

    finally:
        # 清理会话
        session.close()

    # 保存测试日志
    save_logs_to_json(output_dir, output_file, api_logs)
    print("\nOceanStor Pacific NAS API testing completed.")


if __name__ == "__main__":
    # 配置信息
    BASE_URL = "https://oceanstornas-server"  # 替换为实际的OceanStor Pacific NAS服务器地址
    CREDENTIALS = {"username": "admin", "password": "password"}  # 替换为实际的密码
    OUTPUT_DIR = "output"
    OUTPUT_FILE = "oceanstornas-api_result.json"

    # 执行测试
    main(BASE_URL, CREDENTIALS, OUTPUT_DIR, OUTPUT_FILE)
