# -- coding: utf-8 --
# @File: init_data.py
# @Time: 2026/2/6 14:42
# @Author: windyzhao
from copy import deepcopy

from apps.alerts.constants.constants import LevelType, AlertsSourceTypes, AlertAccessType
from apps.alerts.common.source_adapter.constants import (
    DEFAULT_SOURCE_CONFIG,
    build_prometheus_source_config,
    build_zabbix_source_config,
)

DEFAULT_LEVEL = [
    {
        "level_type": LevelType.EVENT,
        "level_id": 0,
        "level_name": "Critical",
        "level_display_name": "严重",
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
        "level_display_name": "警告",
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
        "level_display_name": "严重",
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
        "level_display_name": "警告",
        "color": "#FFAD42",
        "icon": "gantanhao1",
        "description": "",
    },
    {
        "level_type": LevelType.INCIDENT,
        "level_id": 0,
        "level_name": "Critical",
        "level_display_name": "严重",
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
        "level_display_name": "警告",
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


def build_k8s_source_config():
    config = deepcopy(DEFAULT_SOURCE_CONFIG)
    config["params"]["source_id"] = "k8s"
    config["examples"]["CURL"] = config["examples"]["CURL"].replace('"source_id": "restful"', '"source_id": "k8s"')
    config["examples"]["Python"] = config["examples"]["Python"].replace('"source_id": "restful"', '"source_id": "k8s"')
    config["examples"]["CURL"] = config["examples"]["CURL"].replace('"push_source_id": "zabbix"',
                                                                    '"push_source_id": "k8s"')
    config["examples"]["Python"] = config["examples"]["Python"].replace('"push_source_id": "zabbix"',
                                                                        '"push_source_id": "k8s"')
    config["event_fields_desc_mapping"]["push_source_id"] = (
        "事件来源 | 类型: string | 必填: 否(默认k8s) | 说明: 标记具体由哪个K8s推送链路或上游模块推送, 默认为k8s, 支持用户在YAML中修改"
    )
    return config


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
        "description": "内置NATS告警源, 通过NATS网关接收数据",
        "logo": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBzdGFuZGFsb25lPSJubyI/PjwhRE9DVFlQRSBzdmcgUFVCTElDICItLy9XM0MvL0RURCBTVkcgMS4xLy9FTiIgImh0dHA6Ly93d3cudzMub3JnL0dyYXBoaWNzL1NWRy8xLjEvRFREL3N2ZzExLmR0ZCI+PHN2ZyB0PSIxNzQ5NTM4Mjk5NTYwIiBjbGFzcz0iaWNvbiIgdmlld0JveD0iMCAwIDEwMjQgMTAyNCIgdmVyc2lvbj0iMS4xIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHAtaWQ9IjE0ODQ2IiB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayIgd2lkdGg9IjIwMCIgaGVpZ2h0PSIyMDAiPjxwYXRoIGQ9Ik0xMTMuOSA5Ny4xdjY0Ni40aDMzOS40TDY0NyA5MjcuMVY3NDMuNmgyNjJWOTcuMUgxMTMuOXpNNzcyIDU5NC4ySDYyNUwzMzEuMiAzMjQuOXYyNjkuM2gtOTUuNVYyNDguOWgxNTYuN2wyODYuNSAyNjMuMlYyNDguOWg5M2wwLjEgMzQ1LjN6IiBmaWxsPSIjZmZmZmZmIiBwLWlkPSIxNDg0NyIgZGF0YS1zcG0tYW5jaG9yLWlkPSJhMzEzeC5zZWFyY2hfaW5kZXguMC5pMC4xMTczM2E4MWpVNTlzSSIgY2xhc3M9InNlbGVjdGVkIj48L3BhdGg+PC9zdmc+"
    },
    {
        "name": "Prometheus",
        "source_id": "prometheus",
        "source_type": AlertsSourceTypes.PROMETHEUS,
        "config": build_prometheus_source_config("prometheus"),
        "access_type": AlertAccessType.BUILT_IN,
        "is_active": True,
        "is_effective": True,
        "description": "内置Prometheus告警源, 支持Alertmanager默认webhook并自动转换为标准事件",
        "logo": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBzdGFuZGFsb25lPSJubyI/PjwhRE9DVFlQRSBzdmcgUFVCTElDICItLy9XM0MvL0RURCBTVkcgMS4xLy9FTiIgImh0dHA6Ly93d3cudzMub3JnL0dyYXBoaWNzL1NWRy8xLjEvRFREL3N2ZzExLmR0ZCI+PHN2ZyB0PSIxNzc3MDE5MzE1Mzc1IiBjbGFzcz0iaWNvbiIgdmlld0JveD0iMCAwIDEwMjQgMTAyNCIgdmVyc2lvbj0iMS4xIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHAtaWQ9IjI2NDciIHhtbG5zOnhsaW5rPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5L3hsaW5rIiB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCI+PHBhdGggZD0iTTUxMi4xNzYgOTYwLjM1MmMyNDcuNTIgMCA0NDguMTc2LTIwMC42NCA0NDguMTc2LTQ0OC4xNkM5NjAuMzUyIDI2NC42NCA3NTkuNzEyIDY0IDUxMi4xOTIgNjQgMjY0LjY0IDY0IDY0IDI2NC42NTYgNjQgNTEyLjE3NmMwIDI0Ny41MiAyMDAuNjU2IDQ0OC4xNzYgNDQ4LjE3NiA0NDguMTc2eiIgZmlsbD0iI0U2NTMyQyIgcC1pZD0iMjY0OCI+PC9wYXRoPjxwYXRoIGQ9Ik02MzcuNTM2IDU2My42OHM0NS44MDgtNDAuMTQ0IDQ1LjgwOC0xMDIuMjg4YzAtMTkuNTItMC43MDQtNTcuMTY4LTEyLjQzMi05MC41Ni0xNC4xOTItNDAuNDgtNDAuNDgtNzguMTI4LTUwLjQxNi0xMTYuMTI4LTcuODI0LTI5LjgyNC0yLjEyOC01Mi4yMDggMC43MDQtNjguNTQ0IDAgMC01Ni40NjQgMjEuMzEyLTU5LjY2NCAyMDIuNDMyIDAgMCAwLjM1Mi00Ny41ODQtOS4yMzItOTUuMTY4LTguMTYtNDAuODQ4LTM0LjgtOTEuNjMyLTQzLjMyOC0xMjYuNzg0LTcuNDU2LTMwLjU2IDEuNzc2LTQ3LjYgMy4yLTUyLjkyOCAwIDAtMzEuOTY4IDUuNjk2LTQ1LjEwNCA0NC4wNDgtMTcuMzkyIDUxLjg0LTcuMTA0IDc0LjIyNC0xNy4wNCAxMTguOTYtOC41MjggMzgtMjMuNzkyIDY0LjY0LTI5LjEyIDY5Ljk2OCAwIDAgMS40MDgtMTI4LjIwOC01My4yOC0xMjkuMjggMCAwIDE1LjYzMiAyNC4xNiAzLjIgNjUuMzYtMTIuMDggMzkuNzc2LTQzLjMyOCA5NC44MTYtNDcuNTg0IDE0OC4wOC00LjI3MiA1My42MzIgMjMuMDcyIDEwOS4zOTIgNDQuMzg0IDEzMi40OGwtMTM2LjM2OC0yOC4wNjRzMjQuODY0IDc1LjI4IDY3LjEyIDExMC44SDcxNy40NHM0Ny4yMzItMzcuNjQ4IDY5LjYtMTEwLjhsLTE0OS41MDQgMjguNDE2ek0yOTcuNjggNzY0LjY1Nmg0MjQuMzg0di03OS4ySDI5Ny42OHY3OS4yeiBtMjExLjI5NiAxMzkuOTJjNjkuMjQ4IDAgMTI1LjcyOC00Ny4yMzIgMTMwLjMzNi0xMDYuNTI4bC0yNjEuMDI0LTEuNzc2YzMuNTUyIDYwLjM2OCA2MC43MzYgMTA4LjMyIDEzMC42ODggMTA4LjMyeiIgZmlsbD0iI0ZGRkZGRiIgcC1pZD0iMjY0OSI+PC9wYXRoPjwvc3ZnPg=="
    },
    {
        "name": "Zabbix",
        "source_id": "zabbix",
        "source_type": AlertsSourceTypes.ZABBIX,
        "config": build_zabbix_source_config("zabbix"),
        "access_type": AlertAccessType.BUILT_IN,
        "is_active": True,
        "is_effective": True,
        "description": "内置Zabbix告警源, 支持Webhook Media Type并以ProblemId进行告警恢复闭环",
        "logo": "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBzdGFuZGFsb25lPSJubyI/PjwhRE9DVFlQRSBzdmcgUFVCTElDICItLy9XM0MvL0RURCBTVkcgMS4xLy9FTiIgImh0dHA6Ly93d3cudzMub3JnL0dyYXBoaWNzL1NWRy8xLjEvRFREL3N2ZzExLmR0ZCI+PHN2ZyB0PSIxNzc3MDE5Mjc4NTQ3IiBjbGFzcz0iaWNvbiIgdmlld0JveD0iMCAwIDMwNzIgMTAyNCIgdmVyc2lvbj0iMS4xIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHAtaWQ9IjE2NDYiIHhtbG5zOnhsaW5rPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5L3hsaW5rIiB3aWR0aD0iNjAwIiBoZWlnaHQ9IjIwMCI+PHBhdGggZD0iTTAgNzYuOGgzMDcydjg3MC40SDB6IiBmaWxsPSIjRTQwMDAwIiBwLWlkPSIxNjQ3Ij48L3BhdGg+PHBhdGggZD0iTTY4OC42NCA3OTEuMDR2LTUzLjc2SDM0My4wNGwzMjcuNjgtNDI3LjUydi01MS4yaC0zODR2NTMuNzZoMzA3LjJMMjYzLjY4IDc0Mi40djUxLjJoNDI0Ljk2eiBtODEuOTIgMGw1Ni4zMi0xNDguNDhoMjQwLjY0bDU2LjMyIDE0OC40OGg2Ni41NmwtMjA3LjM2LTUzMi40OGgtNjkuMTJsLTIwNy4zNiA1MzIuNDhoNjR6TTEwNDkuNiA1OTEuMzZoLTIwNC44bDEwMi40LTI2Ni4yNGgyLjU2TDEwNDkuNiA1OTEuMzZ6IG00MjcuNTIgMTk5LjY4YzUzLjc2IDAgOTcuMjgtMTAuMjQgMTI4LTMzLjI4IDM1Ljg0LTI1LjYgNTMuNzYtNjQgNTMuNzYtMTE1LjIgMC0zNS44NC0xMC4yNC02NC0zMC43Mi04Ny4wNC0xNy45Mi0yMy4wNC00Ni4wOC0zOC40LTc5LjM2LTQzLjUyIDI1LjYtNy42OCA0OC42NC0yMy4wNCA2NC00My41MiAxNS4zNi0yMC40OCAyMy4wNC00OC42NCAyMy4wNC03Ni44IDAtNDAuOTYtMTIuOC03NC4yNC00MC45Ni05Ny4yOC0yOC4xNi0yMy4wNC02Ni41Ni0zNS44NC0xMTcuNzYtMzUuODRoLTIzNS41MnY1MzIuNDhoMjM1LjUyeiBtLTEyLjgtMjk5LjUySDEzMDUuNnYtMTgxLjc2aDE2MS4yOGMzNS44NCAwIDY0IDcuNjggODQuNDggMjAuNDggMTcuOTIgMTUuMzYgMjguMTYgMzguNCAyOC4xNiA2Ni41NiAwIDMwLjcyLTEwLjI0IDUzLjc2LTMwLjcyIDY5LjEyLTIwLjQ4IDE3LjkyLTQ4LjY0IDI1LjYtODQuNDggMjUuNnogbTcuNjggMjQ4LjMyaC0xNjguOTZ2LTE5Ny4xMmgxNjguOTZjNDAuOTYgMCA3MS42OCA3LjY4IDkyLjE2IDIzLjA0IDIzLjA0IDE1LjM2IDMzLjI4IDQwLjk2IDMzLjI4IDc2LjggMCAzMy4yOC0xMi44IDYxLjQ0LTM4LjQgNzYuOC0yMC40OCAxMi44LTUxLjIgMjAuNDgtODcuMDQgMjAuNDh6IG01MDQuMzIgNTEuMmM1My43NiAwIDk3LjI4LTEwLjI0IDEyOC0zMy4yOCAzNS44NC0yNS42IDUzLjc2LTY0IDUzLjc2LTExNS4yIDAtMzUuODQtMTAuMjQtNjQtMzAuNzItODcuMDQtMTcuOTItMjMuMDQtNDYuMDgtMzguNC03OS4zNi00My41MiAyNS42LTcuNjggNDguNjQtMjMuMDQgNjQtNDMuNTIgMTUuMzYtMjAuNDggMjMuMDQtNDguNjQgMjMuMDQtNzYuOCAwLTQwLjk2LTEyLjgtNzQuMjQtNDAuOTYtOTcuMjgtMjguMTYtMjMuMDQtNjYuNTYtMzUuODQtMTE3Ljc2LTM1Ljg0SDE3NDAuOHY1MzIuNDhoMjM1LjUyeiBtLTEyLjgtMjk5LjUyaC0xNTguNzJ2LTE4MS43NmgxNjEuMjhjMzUuODQgMCA2NCA3LjY4IDg0LjQ4IDIwLjQ4IDE3LjkyIDE1LjM2IDI4LjE2IDM4LjQgMjguMTYgNjYuNTYgMCAzMC43Mi0xMC4yNCA1My43Ni0zMC43MiA2OS4xMi0yMC40OCAxNy45Mi00OC42NCAyNS42LTg0LjQ4IDI1LjZ6IG03LjY4IDI0OC4zMmgtMTY4Ljk2di0xOTcuMTJIMTk3MS4yYzQwLjk2IDAgNzEuNjggNy42OCA5Mi4xNiAyMy4wNCAyMy4wNCAxNS4zNiAzMy4yOCA0MC45NiAzMy4yOCA3Ni44IDAgMzMuMjgtMTIuOCA2MS40NC0zOC40IDc2LjgtMjAuNDggMTIuOC01MS4yIDIwLjQ4LTg3LjA0IDIwLjQ4eiBtMzM1LjM2IDUxLjJWMjU4LjU2aC01OC44OHY1MzIuNDhoNTguODh6IG0xMzUuNjggMGwxNTYuMTYtMjI3Ljg0IDE1Ni4xNiAyMjcuODRoNzQuMjRsLTE5NC41Ni0yNzYuNDggMTgxLjc2LTI1NmgtNzQuMjRsLTE0My4zNiAyMDcuMzYtMTQzLjM2LTIwNy4zNkgyMzgwLjhsMTc5LjIgMjU2LTE5NC41NiAyNzYuNDhoNzYuOHoiIGZpbGw9IiNGRkZGRkYiIHAtaWQ9IjE2NDgiPjwvcGF0aD48L3N2Zz4="
    }, {
        "name": "K8s",
        "source_id": "k8s",
        "source_type": AlertsSourceTypes.RESTFUL,
        "config": build_k8s_source_config(),
        "access_type": AlertAccessType.BUILT_IN,
        "is_active": True,
        "is_effective": True,
        "description": "内置K8s告警源, Kubernetes Event Exporter 可通过此通道推送事件",
        "logo": "/assets/icons/mm-k8s_K8S.svg",
    }
]
