# -- coding: utf-8 --
# @File: init_constants.py
# @Time: 2025/6/26 10:53
# @Author: windyzhao

# 告警丰富设置常量
INIT_ALERT_ENRICH = "alert_enrich"

# 系统设置
SYSTEM_SETTINGS = [
    {
        "key": "no_dispatch_alert_notice",
        "value": {
            "notify_every": 60,
            "notify_people": [],
            "notify_channel": []
        },
        "description": " 未分派告警通知设置",
        "is_activate": False,
        "is_build": True
    },
    {
        "key": INIT_ALERT_ENRICH,
        "value": {
            "enable": True,
        },
        "description": " 告警丰富设置",
        "is_activate": True,
        "is_build": True
    }
]
