# -- coding: utf-8 --
# @File: constants.py
# @Time: 2025/5/14 13:49
# @Author: windyzhao

from copy import deepcopy

DEFAULT_SOURCE_CONFIG = {
    "url": "/api/v1/alerts/api/receiver_data/",
    "headers": {"SECRET": "your_source_secret"},
    "params": {"source_id": "", "events": []},
    "examples": {
        "CURL": """
        curl --location --request POST '{url}/api/v1/alerts/api/receiver_data/' \
        --header 'SECRET: {SECRET}' \
        --header 'Content-Type: application/json' \
        --data-raw '{
          "source_id": "restful",
          "events": [
            {
              "push_source_id": "zabbix",
              "title": "Jenkins流水线 frontend-deploy 构建状态成功1",
              "description": "流水线: frontend-deploy 状态: 成功",
              "value": 0,
              "item": "jenkins_build_status",
              "level": "1",
              "start_time": "1751964596",
              "service": "server_01",
              "location": "shanghai",
              "labels": {
                "pipeline": "frontend-deploy",
                "build_number": "7",
                "external_id": "5755b65d-3cdc-47ed-90de-834db7a58e26",
                "status": 0,
                "resource_id": 1,
                "resource_type": "jenkins_pipeline",
                "resource_name": "frontend-deploy"
              }
            }
          ]
        }'
        """,
        "Python": """
        import requests
        import json
        
        url = "{url}/api/v1/alerts/api/receiver_data/"
        
        payload = json.dumps({
           "source_id": "restful",
           "events": [
              {
                "push_source_id": "zabbix",
                  "title": "Jenkins流水线 frontend-deploy 构建状态成功1",
                  "description": "流水线: frontend-deploy 状态: 成功",
                  "value": 0,
                 "item": "jenkins_build_status",
                 "level": "1",
                 "start_time": "1751964596",
                 "service": "server_01",
                 "location": "shanghai",
                 "labels": {
                    "pipeline": "frontend-deploy",
                    "build_number": "7",
                    "external_id": "5755b65d-3cdc-47ed-90de-834db7a58e26",
                    "status": 0,
                    "resource_id": 1,
                    "resource_type": "jenkins_pipeline",
                    "resource_name": "frontend-deploy"
                 }
              }
           ]
        })
        headers = {
           'SECRET': '{SECRET}',
           'Content-Type': 'application/json'
        }
        
        response = requests.request("POST", url, headers=headers, data=payload)
        
        print(response.text)

        """,
    },
    "content_type": "application/json",
    "method": "POST",
    "timeout": 30,
    "auth": {
        "type": "",
        "token": "your_token_here",
        "username": "user",
        "password": "pass",
        "secret_key": "your_secret",
    },
    "event_fields_mapping": {
        "title": "title",
        "description": "description",
        "level": "level",
        "item": "item",
        "start_time": "start_time",
        "end_time": "end_time",
        "labels": "labels",
        "rule_id": "rule_id",
        "external_id": "external_id",
        "push_source_id": "push_source_id",
        "resource_id": "resource_id",
        "resource_name": "resource_name",
        "resource_type": "resource_type",
        "value": "value",
        "action": "action",
        "service": "service",
        "tags": "tags",
        "location": "location",
    },
    "event_fields_desc_mapping": {
        "title": "事件标题 | 类型: string | 必填: 是",
        "description": "事件描述 | 类型: string | 必填: 否",
        "level": "事件级别 | 类型: string | 必填: 否(默认最低级别) | 可选值: 0-致命, 1-错误, 2-预警, 3-提醒",
        "item": "事件指标 | 类型: string | 必填: 否",
        "value": "事件值 | 类型: float | 必填: 否",
        "start_time": "事件开始时间 | 类型: string(时间戳) | 必填: 否(默认当前时间) | 格式: 秒级(10位)或毫秒级(13位)",
        "end_time": "事件结束时间 | 类型: string(时间戳) | 必填: 否 | 格式: 秒级(10位)或毫秒级(13位)",
        "action": "事件动作 | 类型: string | 必填: 否(默认created) | 可选值: created-创建, closed-关闭, recovery-恢复",
        "external_id": "外部事件ID(指纹) | 类型: string | 必填: 否(不传则自动生成) | 说明: 用于事件恢复关联",
        "push_source_id": "事件来源 | 类型: string | 必填: 否(默认default) | 说明: 标记事件由哪个上游系统或模块推送, 例如zabbix, prometheus等",
        "service": "所属服务 | 类型: string | 必填: 否",
        "location": "事件发生位置 | 类型: string | 必填: 否",
        "tags": "事件标签 | 类型: object | 必填: 否",
        "labels": "事件元数据 | 类型: object | 必填: 否 | 说明: 可包含资源关联等扩展信息",
        "rule_id": "触发规则ID | 类型: string | 必填: 否",
        "resource_id": "资源ID | 类型: string | 必填: 否",
        "resource_name": "资源名称 | 类型: string | 必填: 否",
        "resource_type": "资源类型 | 类型: string | 必填: 否",
    },
}


def build_prometheus_source_config(source_id):
    config = deepcopy(DEFAULT_SOURCE_CONFIG)
    config.update(
        {
  "url": f"/api/v1/alerts/api/source/{source_id}/webhook/",
            "headers": {"SECRET": "your_source_secret"},
            "params": {
                "receiver": "bk-lite-prometheus",
                "status": "firing",
                "commonLabels": {"alertname": "HighCPUUsage", "severity": "critical"},
                "commonAnnotations": {"summary": "CPU too high"},
                "alerts": [],
            },
            "examples": {
                "CURL": f"""
        curl --location --request POST '{{url}}/api/v1/alerts/api/source/{source_id}/webhook/' \n
        --header 'SECRET: {{SECRET}}' \n
        --header 'Content-Type: application/json' \n
        --data-raw '{{
          "receiver": "bk-lite-prometheus",
          "status": "firing",
          "commonLabels": {{
            "alertname": "HighCPUUsage",
            "severity": "critical"
          }},
          "commonAnnotations": {{
            "summary": "CPU too high"
          }},
          "alerts": [
            {{
              "status": "firing",
              "labels": {{
                "instance": "node-1",
                "job": "node-exporter"
              }},
              "annotations": {{
                "description": "node-1 cpu usage > 90%"
              }},
              "startsAt": "2026-04-22T08:00:00Z",
              "endsAt": "2026-04-22T09:00:00Z"
            }}
          ]
        }}'
        """,
                "Python": f"""
        import json
        import requests

        url = "{{url}}/api/v1/alerts/api/source/{source_id}/webhook/"
        payload = {{
            "receiver": "bk-lite-prometheus",
            "status": "firing",
            "commonLabels": {{"alertname": "HighCPUUsage", "severity": "critical"}},
            "commonAnnotations": {{"summary": "CPU too high"}},
            "alerts": [
                {{
                    "status": "firing",
                    "labels": {{"instance": "node-1", "job": "node-exporter"}},
                    "annotations": {{"description": "node-1 cpu usage > 90%"}},
                    "startsAt": "2026-04-22T08:00:00Z",
                    "endsAt": "2026-04-22T09:00:00Z"
                }}
            ]
        }}
        headers = {{"SECRET": "{{SECRET}}", "Content-Type": "application/json"}}
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        print(response.text)
        """,
            },
            "accept_default_payload": True,
            "accept_custom_payload": True,
            "send_resolved_required": True,
        }
    )
    return config


def build_zabbix_source_config(source_id):
    config = deepcopy(DEFAULT_SOURCE_CONFIG)
    config.update(
        {
  "url": f"/api/v1/alerts/api/source/{source_id}/webhook/",
            "headers": {"SECRET": "your_source_secret"},
            "params": {
                "Subject": "Zabbix CPU High",
                "Message": "cpu usage > 90%",
                "Severity": "3",
                "TriggerName": "system.cpu.util",
                "ProblemId": "10002",
                "EventId": "20002",
                "TriggerId": "30002",
                "HostId": "40002",
                "HostName": "host-2",
                "EventValue": "1",
            },
            "examples": {
                "CURL": f"""
        curl --location --request POST '{{url}}/api/v1/alerts/api/source/{source_id}/webhook/' \n
        --header 'SECRET: {{SECRET}}' \n
        --header 'Content-Type: application/json' \n
        --data-raw '{{
          "Subject": "Zabbix CPU High",
          "Message": "cpu usage > 90%",
          "Severity": "3",
          "TriggerName": "system.cpu.util",
          "ProblemId": "10002",
          "EventId": "20002",
          "TriggerId": "30002",
          "HostId": "40002",
          "HostName": "host-2",
          "EventValue": "1"
        }}'
        """,
                "Python": f"""
        import json
        import requests

        url = "{{url}}/api/v1/alerts/api/source/{source_id}/webhook/"
        payload = {{
            "Subject": "Zabbix CPU High",
            "Message": "cpu usage > 90%",
            "Severity": "3",
            "TriggerName": "system.cpu.util",
            "ProblemId": "10002",
            "EventId": "20002",
            "TriggerId": "30002",
            "HostId": "40002",
            "HostName": "host-2",
            "EventValue": "1"
        }}
        headers = {{"SECRET": "{{SECRET}}", "Content-Type": "application/json"}}
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        print(response.text)
        """,
            },
            "accept_problem": True,
            "accept_recovery": True,
            "accept_update": False,
            "external_id_mode": "problem_id",
            "recovery_policy": "problem_id_match",
        }
    )
    return config
