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
            session.headers.update(
                {"X-Auth-Token": token, "Content-Type": "application/json", "Accept": "application/json"}
            )
    return response


@log_api_call
def test_get_pools(base_url):
    """测试获取存储池列表"""
    url = f"{base_url}/api/v2/block_service/volumes"
    return session.get(url, verify=False)


@log_api_call
def test_get_performance_data(base_url, object_type="10", metrics=None):
    """测试获取性能数据"""
    url = f"{base_url}/api/v2/pms/performance_data"
    if not metrics:
        metrics = ["22", "25", "28", "370", "123", "124", "428", "430", "432"]

    data = {
        "begin_time": int(time.time() - 900),  # 15分钟前
        "end_time": int(time.time()),
        "objects": [{"object_type": object_type, "ids": ["*"], "indicators": metrics}],
    }
    return session.post(url, json=data, verify=False)


def test_metrics_extraction(response):
    """测试指标数据提取"""
    metrics_map = {
        "22": "io_rate",
        "25": "read_io",
        "28": "write_io",
        "370": "resp_t",
        "123": "read",
        "124": "write",
        "428": "resp_t",
        "430": "resp_t_w",
        "432": "resp_t_r",
    }

    extracted_metrics = {}
    if response and response.status_code == 200:
        data = response.json()
        for obj in data.get("objects", []):
            obj_id = obj.get("ids", ["unknown"])[0]
            metrics = {}
            for indicator in obj.get("indicators", []):
                metric_id = indicator.get("indicator")
                metric_name = metrics_map.get(metric_id)
                if metric_name:
                    metrics[metric_name] = indicator.get("indicator_values", [])[-1]
            extracted_metrics[obj_id] = metrics
    return extracted_metrics


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
        # 测试获取存储池列表
        print("\nTesting storage pools API...")
        pools_response = test_get_pools(base_url)
        if pools_response and pools_response.status_code == 200:
            print("Storage pools API test successful")

        # 测试性能数据API - 存储池
        print("\nTesting pool performance data API...")
        pool_perf_response = test_get_performance_data(base_url, object_type="216")
        if pool_perf_response and pool_perf_response.status_code == 200:
            print("Pool performance data API test successful")
            metrics = test_metrics_extraction(pool_perf_response)
            print(f"Extracted pool metrics: {metrics}")

        # 测试性能数据API - 磁盘
        print("\nTesting disk performance data API...")
        disk_perf_response = test_get_performance_data(base_url, object_type="10")
        if disk_perf_response and disk_perf_response.status_code == 200:
            print("Disk performance data API test successful")
            metrics = test_metrics_extraction(disk_perf_response)
            print(f"Extracted disk metrics: {metrics}")

    finally:
        # 清理会话
        session.close()

    # 保存测试日志
    save_logs_to_json(output_dir, output_file, api_logs)
    print("\nOceanStor Pacific NAS API testing completed.")


if __name__ == "__main__":
    # 配置信息
    BASE_URL = "https://oceanstorpacificanas-server"  # 替换为实际的服务器地址
    CREDENTIALS = {"username": "admin", "password": "password"}  # 替换为实际的密码
    OUTPUT_DIR = "output"
    OUTPUT_FILE = "oceanstorpacificanas-api_result.json"

    # 执行测试
    main(BASE_URL, CREDENTIALS, OUTPUT_DIR, OUTPUT_FILE)
