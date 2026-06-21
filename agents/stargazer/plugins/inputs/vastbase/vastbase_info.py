# -*- coding: utf-8 -*-
"""海量数据库Vastbase 采集器（企业版，PG兼容）：复用社区 PostgresqlInfo 的连接/SQL，仅重命名 model_id（不臆造）。

DB 采集器按 dameng 范式置社区 plugins/inputs。
"""
from plugins.inputs.postgresql.postgresql_info import PostgresqlInfo


class VastbaseInfo(PostgresqlInfo):
    def list_all_resources(self):
        data = super().list_all_resources()
        result = data.get("result", {}) or {}
        if "postgresql" in result:
            recs = result.pop("postgresql")
            for rec in recs:
                if isinstance(rec, dict) and rec.get("inst_name"):
                    rec["inst_name"] = f"{self.host}-vastbase-{self.port}"
            result["vastbase"] = recs
        return data
