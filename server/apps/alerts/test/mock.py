# -- coding: utf-8 --
# @File: mock.py
# @Time: 2025/5/30 17:32
# @Author: windyzhao


import random
import time
import uuid
import json


def generate_mock_events(num_events=100):
    # 基础数据模板
    base_event = {
        "title": "CPU Usage High",
        "description": "CPU usage exceeded 80%",
        "value": 85.0,
        "item": "cpu_usage",
        "level": "0",
        "start_time": "1747277570",
        "end_time": "1747277574",
        "labels": {
            "instance": "server1"
        },
        "annotations": {
            "alertname": "HighCPUUsage"
        },
        "external_id": "sasasa",
        "status": "firing",
        "resource_id": 1,
        "resource_type": "host",
        "resource_name": "host-1",
    }

    # 可能的变量值
    #

    levels_map = {"0": "Critical", "1": "Error", "2": "Warning", "3": "Info"}
    statuses = ["firing", "resolved"]
    server_prefixes = ["web", "db", "app", "cache", "lb"]

    events = []

    for i in range(num_events):
        # 复制基础事件
        event = base_event.copy()

        now = int(time.time())
        start_time = now - random.randint(0, 5 * 60)
        duration = random.randint(1, 60)  # 1-300秒
        end_time = start_time + duration

        # 随机CPU使用率描述
        cpu_usage = random.randint(65, 100)
        if cpu_usage >= 95:
            level = "0"
        elif cpu_usage >= 90:
            level = "1"  #
        elif cpu_usage >= 80:
            level = "2"
        else:
            level = "3"  #

        # 服务器名称
        server_type = random.choice(server_prefixes)
        server_num = random.randint(1, 20)

        # 更新事件数据
        event["title"] = f"CPU Usage {levels_map[level]}"
        event["description"] = f"CPU usage exceeded {cpu_usage}%"
        event["level"] = level
        event["start_time"] = str(start_time)
        event["end_time"] = str(end_time)
        event["labels"] = {
            "instance": f"host-{server_num}",
            "region": random.choice(["us-east", "us-west", "eu-central", "ap-southeast"])
        }
        event["annotations"] = {
            "alertname": "HighCPUUsage",
            "summary": f"High CPU usage detected on {server_type}-{server_num}",
            "severity": level
        }
        event["external_id"] = str(uuid.uuid4())
        event["status"] = random.choice(statuses)
        event["value"] = float(cpu_usage)
        event["item"] = "cpu_usage"
        event["resource_id"] = server_num
        event["resource_type"] = "host"
        event["resource_name"] = f"host-{server_num}"

        events.append(event)

    # 构建最终数据结构
    result = {
        "source_type": "restful",
        "source_id": "restful",
        "events": events
    }

    return result


def generate_jenkins_failure_events(num_pipelines=5):
    """生成Jenkins构建失败事件，满足连续失败3次的规则"""

    # Jenkins构建事件基础模板
    base_event = {
        "title": "Jenkins Pipeline Build Failed",
        "description": "Jenkins pipeline build failed",
        "value": 0.0,  # 明确设置为0.0，表示构建失败
        "item": "jenkins_build_status",
        "level": "0",
        "start_time": "",
        "end_time": "",
        "labels": {
            "pipeline": "",
            "build_number": ""
        },
        "annotations": {
            "alertname": "JenkinsBuildFailure"
        },
        "external_id": "",
        "status": 0,
        "resource_id": 1,
        "resource_type": "jenkins_pipeline",
        "resource_name": "",
    }

    pipeline_names = [
        "frontend-deploy",
        "backend-api",
        "data-processing",
        "mobile-app",
        "microservice-auth"
    ]

    events = []
    current_time = int(time.time())

    # # 为每个pipeline生成连续失败的事件
    # for i in range(min(num_pipelines, len(pipeline_names))):
    #     pipeline_name = pipeline_names[i]
    #     resource_id = i + 1
    #
    #     # 生成连续3次失败的构建事件
    #     for build_num in range(1, 4):  # 3次连续失败
    #         event = base_event.copy()
    #         event["labels"] = event["labels"].copy()
    #         event["annotations"] = event["annotations"].copy()
    #
    #         # 每次构建间隔5-10分钟
    #         build_start_time = current_time - (3 - build_num) * random.randint(300, 600)
    #         build_duration = random.randint(120, 300)  # 构建持续2-5分钟
    #         build_end_time = build_start_time + build_duration
    #
    #         # 更新事件数据
    #         event["title"] = f"Jenkins流水线 {pipeline_name} 连续构建失败"
    #         event["description"] = f"流水线: {pipeline_name}\n构建编号: #{build_num}\n状态: 失败"
    #         event["start_time"] = str(build_start_time)
    #         event["end_time"] = str(build_end_time)
    #         event["labels"]["pipeline"] = pipeline_name
    #         event["labels"]["build_number"] = str(build_num)
    #         event["annotations"]["alertname"] = "JenkinsBuildFailure"
    #         event["annotations"]["pipeline"] = pipeline_name
    #         event["annotations"]["build_number"] = str(build_num)
    #         event["external_id"] = str(uuid.uuid4())
    #         event["status"] = 0  # 失败状态
    #         # 为失败事件设置不同的负值，用于测试
    #         event["value"] = 0
    #         event["resource_id"] = resource_id
    #         event["resource_name"] = pipeline_name
    #
    #         events.append(event)
    #
    # # 添加一些成功的构建事件作为对比
    # for i in range(1):
    #     pipeline_name = random.choice(pipeline_names)
    #     resource_id = pipeline_names.index(pipeline_name) + 1
    #
    #     event = base_event.copy()
    #     event["labels"] = event["labels"].copy()
    #     event["annotations"] = event["annotations"].copy()
    #
    #     success_time = current_time - random.randint(3600, 7200)  # 1-2小时前的成功构建
    #     build_duration = random.randint(60, 180)
    #
    #     event["title"] = f"Jenkins流水线 {pipeline_name} 构建成功"
    #     event["description"] = f"流水线: {pipeline_name}\n状态: 成功"
    #     event["start_time"] = str(success_time)
    #     event["end_time"] = str(success_time + build_duration)
    #     event["labels"]["pipeline"] = pipeline_name
    #     event["labels"]["build_number"] = str(random.randint(10, 50))
    #     event["annotations"]["alertname"] = "JenkinsBuildSuccess"
    #     event["external_id"] = str(uuid.uuid4())
    #     event["status"] = 1  # 成功状态
    #     event["value"] = round(random.uniform(0.5, 1.0), 2)  # 成功值在0.5-1.0之间
    #     event["level"] = "1"
    #     event["resource_id"] = resource_id
    #     event["resource_name"] = pipeline_name
    #     event["value"] = "1"
    #
    #     events.append(event)

    # 添加一些零值事件进行测试
    for i in range(1):
        pipeline_name = pipeline_names[0]  # 使用第一个pipeline
        resource_id = 1

        event = base_event.copy()
        event["labels"] = event["labels"].copy()
        event["annotations"] = event["annotations"].copy()

        zero_time = current_time - random.randint(1800, 3600)  # 30分钟-1小时前
        build_duration = random.randint(60, 120)

        event["title"] = f"Jenkins流水线 {pipeline_name} 构建状态未知"
        event["description"] = f"流水线: {pipeline_name}\n状态: 未知"
        event["start_time"] = str(zero_time)
        event["end_time"] = str(zero_time + build_duration)
        event["labels"]["pipeline"] = pipeline_name
        event["labels"]["build_number"] = str(random.randint(1, 10))
        event["annotations"]["alertname"] = "JenkinsBuildUnknown"
        event["external_id"] = str(uuid.uuid4())
        event["status"] = 0  # 状态为0
        event["value"] = 0  # 明确设置为0.0
        event["level"] = "1"
        event["resource_id"] = resource_id
        event["resource_name"] = pipeline_name

        events.append(event)

    # 按时间排序
    events.sort(key=lambda x: int(x["start_time"]))

    # 构建最终数据结构
    result = {
        "source_type": "restful",
        "source_id": "restful",
        "events": events
    }

    return result


def generate_website_monitoring_events(num_websites=3):
    """生成网站拨测监控事件"""
    base_event = {
        "title": "网站拨测异常",
        "description": "网站拨测状态异常",
        "value": 0,
        "item": "status",
        "level": "1",
        "start_time": "",
        "end_time": "",
        "labels": {
            "url": ""
        },
        "annotations": {
            "alertname": "WebsiteMonitoring"
        },
        "external_id": "",
        "status": "firing",
        "resource_id": 1,
        "resource_type": "网站拨测",
        "resource_name": "",
    }

    websites = [
        {"name": "主站", "url": "https://www.example.com"},
        {"name": "API服务", "url": "https://api.example.com"},
        {"name": "管理后台", "url": "https://admin.example.com"}
    ]

    events = []
    current_time = int(time.time())

    for i in range(min(num_websites, len(websites))):
        website = websites[i]

        # 生成异常事件 (value=0)
        event = base_event.copy()
        event["labels"] = event["labels"].copy()
        event["annotations"] = event["annotations"].copy()

        event_time = current_time - random.randint(60, 300)
        duration = random.randint(30, 120)

        event["title"] = f"网站拨测异常 - {website['name']}"
        event["description"] = f"网站: {website['name']}\n拨测状态: 异常\nURL: {website['url']}"
        event["start_time"] = str(event_time)
        event["end_time"] = str(event_time + duration)
        event["labels"]["url"] = website["url"]
        event["external_id"] = str(uuid.uuid4())
        event["value"] = 0  # 异常状态
        event["resource_id"] = i + 1
        event["resource_name"] = website["name"]

        events.append(event)

        # 生成正常事件 (value=1)
        normal_event = event.copy()
        normal_event["labels"] = normal_event["labels"].copy()

        normal_time = current_time - random.randint(3600, 7200)
        normal_event["title"] = f"网站拨测正常 - {website['name']}"
        normal_event["description"] = f"网站: {website['name']}\n拨测状态: 正常"
        normal_event["start_time"] = str(normal_time)
        normal_event["end_time"] = str(normal_time + 30)
        normal_event["external_id"] = str(uuid.uuid4())
        normal_event["value"] = 1  # 正常状态
        normal_event["level"] = "3"

        events.append(normal_event)

    return {
        "source_type": "restful",
        "source_id": "restful",
        "events": events
    }


if __name__ == "__main__":
    # 生成100个mock事件
    mock_data = generate_mock_events(50)

    with open("mock_monitor_events.json", "w") as f:
        json.dump(mock_data, f, indent=2)

    print("Mock数据已生成并保存到 mock_monitor_events.json 文件")
    #
    # 生成Jenkins失败事件数据，包含0.0和负数测试
    # jenkins_data = generate_jenkins_failure_events(2)
    #
    # # 保存到JSON文件
    # with open("mock_jenkins_failure_events.json", "w", encoding='utf-8') as f:
    #     json.dump(jenkins_data, f, indent=2, ensure_ascii=False)
    #
    # print("Jenkins失败事件Mock数据已生成并保存到 mock_jenkins_failure_events.json 文件")
    # print("数据包含：负数值、0.0值和正数值的测试用例")

    # 生成网站拨测事件数据
    # website_data = generate_website_monitoring_events(3)
    #
    # with open("mock_website_monitoring_events.json", "w", encoding='utf-8') as f:
    #     json.dump(website_data, f, indent=2, ensure_ascii=False)
    #
    # print("网站拨测事件Mock数据已生成并保存到 mock_website_monitoring_events.json 文件")