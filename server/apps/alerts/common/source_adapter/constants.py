# -- coding: utf-8 --
# @File: constants.py
# @Time: 2025/5/14 13:49
# @Author: windyzhao

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
