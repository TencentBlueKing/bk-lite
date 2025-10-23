# -- coding: utf-8 --
# @File: init_constants.py
# @Time: 2025/7/24 17:01
# @Author: windyzhao


INIT_SOURCE_API_DATA = [
    {
        "name": "告警趋势",
        "desc": "查询告警趋势的数据",
        "rest_api": "alert/get_alert_trend_data",
        "params": [
            {
                "name": "time",
                "type": "timeRange",
                "value": 10080,
                "alias_name": "time",
                "filterType": "filter"
            },
            {
                "name": "group_by",
                "type": "string",
                "value": "day",
                "alias_name": "group_by",
                "filterType": "fixed"
            }

        ]

    }
]

INIT_NAMESPACE_DATA = [
    {
        "name": "默认命名空间",
        "desc": "系统初始化创建的默认命名空间",
        "is_active": True,
        "created_by": "system",
        "updated_by": "system"
    }
]

INIT_TAG_DATA = [
    {"tag_id": "cmdb",
     "name": "CMDB",
     "desc": "",
     "build_in": True,
     "created_by": "system",
     "updated_by": "system"
     },
    {"tag_id": "alerts",
     "name": "告警",
     "desc": "",
     "build_in": True,
     "created_by": "system",
     "updated_by": "system"
     },
    {"tag_id": "monitor",
     "name": "监控",
     "desc": "",
     "build_in": True,
     "created_by": "system",
     "updated_by": "system"
     },
    {"tag_id": "log",
     "name": "日志",
     "desc": "",
     "build_in": True,
     "created_by": "system",
     "updated_by": "system"
     },
    {"tag_id": "biz",
     "name": "业务",
     "desc": "",
     "build_in": True,
     "created_by": "system",
     "updated_by": "system"
     },
    {"tag_id": "other",
     "name": "其他",
     "desc": "",
     "build_in": True,
     "created_by": "system",
     "updated_by": "system"
     },
]
