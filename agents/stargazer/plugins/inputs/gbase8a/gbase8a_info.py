# -*- coding: utf-8 -*-
"""GBase 8a 采集器（企业版，MySQL 兼容）：复用社区 MysqlInfo 的连接/SQL，仅重命名 model_id（不臆造）。

GBase 8a(MPP) 兼容 MySQL 协议与 SHOW VARIABLES 语法。DB 采集器按 dameng 范式置社区 plugins/inputs。
"""
from plugins.inputs.mysql.mysql_info import MysqlInfo


class Gbase8aInfo(MysqlInfo):
    def list_all_resources(self):
        data = super().list_all_resources()
        result = data.get("result", {}) or {}
        if "mysql" in result:
            recs = result.pop("mysql")
            for rec in recs:
                if isinstance(rec, dict) and rec.get("inst_name"):
                    rec["inst_name"] = f"{self.host}-gbase8a-{self.port}"
            result["gbase8a"] = recs
        return data
