# -- coding: utf-8 --
# @File: constants.py
# @Time: 2025/5/14 13:49
# @Author: windyzhao

DEFAULT_SOURCE_CONFIG = {
    "url": "/api/v1/alerts/api/receiver_data/",
    "headers": {"SECRET": "your_source_secret"},
    "params": {
        "source_id": "",
        "events": []
    },
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
              "service:"server_01",
              "location":"shanghai",
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
                "service:"server_01",
                "location":"shanghai",
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
        "secret_key": "your_secret"
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
        "location": "location"
    },
    "event_fields_desc_mapping": {
        "title": "事件标题, 类型字符串",
        "item": "事件指标, 类型字符串",
        "description": "事件描述，类型字符串",
        "external_id": "事件ID，类型字符串",
        "value": "事件值，float类型",
        "action": "事件类型，类型字符串，可选值为：{'created':'创建', 'closed':'关闭'}",
        "level": "事件级别，类型字符串，可选值为：{'3': '提醒', '2': '预警', '1': '严重', '0': '致命'}",
        "start_time": "事件开始时间(时间戳，毫秒级)",
        "end_time": "事件开始时间(时间戳，毫秒级)",
        "labels": "标签，格式为字典，可选，可以包含其他的所有冗余字段，如关联的资产实例",
        "rule_id": "事件规则ID，类型字符串，可选",
        "resource_id": "资源ID，类型字符串，可选",
        "resource_name": "资源实例名称，类型字符串，可选",
        "resource_type": "资源类型，类型字符串，可选",
        "service": "事件所属服务",
        "tags": "事件标签",
        "location": "事件发生地点"
    }
}
