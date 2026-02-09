# -- coding: utf-8 --
# @File: init_data.py
# @Time: 2026/2/6 14:42
# @Author: windyzhao
from apps.alerts.constants.constants import LevelType, AlertsSourceTypes, AlertAccessType
from apps.alerts.common.source_adapter.constants import DEFAULT_SOURCE_CONFIG

DEFAULT_LEVEL = [
    {
        "level_type": LevelType.EVENT,
        "level_id": 0,
        "level_name": "Critical",
        "level_display_name": "致命",
        "color": "#F43B2C",
        "icon": "huoyanhuodongtuijian",
        "description": "",
    },
    {
        "level_type": LevelType.EVENT,
        "level_id": 1,
        "level_name": "Error",
        "level_display_name": "错误",
        "color": "#D97007",
        "icon": "weiwangguanicon-defuben-",
        "description": "",
    },
    {
        "level_type": LevelType.EVENT,
        "level_id": 2,
        "level_name": "Warning",
        "level_display_name": "预警",
        "color": "#FFAD42",
        "icon": "gantanhao1",
        "description": "",
    },
    {
        "level_type": LevelType.EVENT,
        "level_id": 3,
        "level_name": "Info",
        "level_display_name": "提醒",
        "color": "#FBBF24",
        "icon": "tixing",
        "description": "",
    },
    {
        "level_type": LevelType.ALERT,
        "level_id": 0,
        "level_name": "Critical",
        "level_display_name": "致命",
        "color": "#F43B2C",
        "icon": "huoyanhuodongtuijian",
        "description": "",
    },
    {
        "level_type": LevelType.ALERT,
        "level_id": 1,
        "level_name": "Error",
        "level_display_name": "错误",
        "color": "#D97007",
        "icon": "weiwangguanicon-defuben-",
        "description": "",
    },
    {
        "level_type": LevelType.ALERT,
        "level_id": 2,
        "level_name": "Warning",
        "level_display_name": "预警",
        "color": "#FFAD42",
        "icon": "gantanhao1",
        "description": "",
    },
    {
        "level_type": LevelType.INCIDENT,
        "level_id": 0,
        "level_name": "Critical",
        "level_display_name": "致命",
        "color": "#F43B2C",
        "icon": "huoyanhuodongtuijian",
        "description": "",
    },
    {
        "level_type": LevelType.INCIDENT,
        "level_id": 1,
        "level_name": "Error",
        "level_display_name": "错误",
        "color": "#D97007",
        "icon": "weiwangguanicon-defuben-",
        "description": "",
    },
    {
        "level_type": LevelType.INCIDENT,
        "level_id": 2,
        "level_name": "Warning",
        "level_display_name": "预警",
        "color": "#FFAD42",
        "icon": "gantanhao1",
        "description": "",
    },
]

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

# 内置告警源配置
BUILTIN_ALERT_SOURCES = [
    {
        "name": "RESTful",
        "source_id": "restful",
        "source_type": AlertsSourceTypes.RESTFUL,
        "config": DEFAULT_SOURCE_CONFIG,
        "access_type": AlertAccessType.BUILT_IN,
        "is_active": True,
        "is_effective": True,
        "description": "内置的restful告警源, 监控系统可以通过RESTful API的方式推送EVENT",
        "logo": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBzdGFuZGFsb25lPSJubyI/PjwhRE9DVFlQRSBzdmcgUFVCTElDICItLy9XM0MvL0RURCBTVkcgMS4xLy9FTiIgImh0dHA6Ly93d3cudzMub3JnL0dyYXBoaWNzL1NWRy8xLjEvRFREL3N2ZzExLmR0ZCI+PHN2ZyB0PSIxNzQ5NTM0NTkzMTIyIiBjbGFzcz0iaWNvbiIgdmlld0JveD0iMCAwIDEwMjQgMTAyNCIgdmVyc2lvbj0iMS4xIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHAtaWQ9IjEwNzM5IiB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayIgd2lkdGg9IjIwMCIgaGVpZ2h0PSIyMDAiPjxwYXRoIGQ9Ik0yNDEuMzc5NTU2IDQyMC40MDg4ODlsMzYyLjA0MDg4OCAzNjIuMDk3Nzc4LTEwMC41Nzk1NTUgMTAwLjU3OTU1NWEyNTYgMjU2IDAgMCAxLTM0MC43NjQ0NDUgMTkuMDAwODg5bC0xMjEuODU2IDEyMS43NDIyMjJMMCA5ODMuNjA4ODg5bDEyMS43OTkxMTEtMTIxLjc0MjIyMmEyNTYgMjU2IDAgMCAxIDE5LjAwMDg4OS0zNDAuODIxMzM0TDI0MS4zNzk1NTYgNDIwLjQwODg4OXogbS0wLjA1Njg4OSA4MC40NDA4ODlsLTYwLjMwMjIyMyA2MC40MTZhMTk5LjExMTExMSAxOTkuMTExMTExIDAgMCAwIDI3My4wNjY2NjcgMjg5LjU2NDQ0NGw4LjUzMzMzMy03Ljk2NDQ0NCA2MC4zMDIyMjMtNjAuNDE2LTI4MS42LTI4MS42ek05ODMuMzI0NDQ0IDBsNDAuMjIwNDQ1IDQwLjIyMDQ0NC0xMjEuNzQyMjIyIDEyMS43OTkxMTJhMjU2IDI1NiAwIDAgMS0xOS4wNTc3NzggMzQwLjc2NDQ0NGwtMTAwLjUyMjY2NyAxMDAuNjM2NDQ0LTM2Mi4wNDA4ODktMzYyLjA0MDg4OCAxMDAuNTc5NTU2LTEwMC41Nzk1NTZhMjU2IDI1NiAwIDAgMSAzNDAuODIxMzMzLTE5LjAwMDg4OUw5ODMuMzI0NDQ0IDB6TTU2OS40NTc3NzggMTcyLjk0MjIyMmwtOC41MzMzMzQgOC4wNzgyMjItNjAuMzAyMjIyIDYwLjMwMjIyMyAyODEuNiAyODEuNiA2MC4zMDIyMjItNjAuMzAyMjIzYTE5OS4xMTExMTEgMTk5LjExMTExMSAwIDAgMCA4LjA3ODIyMy0yNzMuMDY2NjY2bC04LjA3ODIyMy04LjUzMzMzNGExOTkuMTExMTExIDE5OS4xMTExMTEgMCAwIDAtMjczLjA2NjY2Ni04LjAyMTMzM3oiIGZpbGw9IiNmZmZmZmYiIHAtaWQ9IjEwNzQwIiBkYXRhLXNwbS1hbmNob3ItaWQ9ImEzMTN4Lm1hbmFnZV90eXBlX215cHJvamVjdHMuMC5pNS4yMjE5M2E4MU50bW9iSiIgY2xhc3M9InNlbGVjdGVkIj48L3BhdGg+PHBhdGggZD0iTTQwNS4yNzY0NDQgNDE3LjczNTExMWw0MC4yMjA0NDUgNDAuMjIwNDQ1LTEyMC42NjEzMzMgMTIwLjY2MTMzMy00MC4yNzczMzQtNDAuMjIwNDQ1ek01NjYuMTU4MjIyIDU3OC41Nmw0MC4yMjA0NDUgNDAuMjc3MzMzLTEyMC42NjEzMzQgMTIwLjY2MTMzNC00MC4yMjA0NDQtNDAuMjIwNDQ1eiIgZmlsbD0iI2ZmZmZmZiIgcC1pZD0iMTA3NDEiIGRhdGEtc3BtLWFuY2hvci1pZD0iYTMxM3gubWFuYWdlX3R5cGVfbXlwcm9qZWN0cy4wLmk2LjIyMTkzYTgxTnRtb2JKIiBjbGFzcz0ic2VsZWN0ZWQiPjwvcGF0aD48L3N2Zz4="
    },
    {
        "name": "NATS",
        "source_id": "nats",
        "source_type": AlertsSourceTypes.NATS,
        "config": DEFAULT_SOURCE_CONFIG,
        "access_type": AlertAccessType.BUILT_IN,
        "is_active": True,
        "is_effective": True,
        "description": "内置NATS告警源, 周期拉取NATS网关数据",
        "logo": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBzdGFuZGFsb25lPSJubyI/PjwhRE9DVFlQRSBzdmcgUFVCTElDICItLy9XM0MvL0RURCBTVkcgMS4xLy9FTiIgImh0dHA6Ly93d3cudzMub3JnL0dyYXBoaWNzL1NWRy8xLjEvRFREL3N2ZzExLmR0ZCI+PHN2ZyB0PSIxNzQ5NTM4Mjk5NTYwIiBjbGFzcz0iaWNvbiIgdmlld0JveD0iMCAwIDEwMjQgMTAyNCIgdmVyc2lvbj0iMS4xIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHAtaWQ9IjE0ODQ2IiB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayIgd2lkdGg9IjIwMCIgaGVpZ2h0PSIyMDAiPjxwYXRoIGQ9Ik0xMTMuOSA5Ny4xdjY0Ni40aDMzOS40TDY0NyA5MjcuMVY3NDMuNmgyNjJWOTcuMUgxMTMuOXpNNzcyIDU5NC4ySDYyNUwzMzEuMiAzMjQuOXYyNjkuM2gtOTUuNVYyNDguOWgxNTYuN2wyODYuNSAyNjMuMlYyNDguOWg5M2wwLjEgMzQ1LjN6IiBmaWxsPSIjZmZmZmZmIiBwLWlkPSIxNDg0NyIgZGF0YS1zcG0tYW5jaG9yLWlkPSJhMzEzeC5zZWFyY2hfaW5kZXguMC5pMC4xMTczM2E4MWpVNTlzSSIgY2xhc3M9InNlbGVjdGVkIj48L3BhdGg+PC9zdmc+"
    }
]
