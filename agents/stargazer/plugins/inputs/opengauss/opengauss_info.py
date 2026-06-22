# -*- coding: utf-8 -*-
"""openGauss 采集器（企业版，PG 兼容）。

openGauss 基于 PostgreSQL、wire 协议兼容，复用社区 PostgresqlInfo 的连接/SQL（SHOW server_version 等），
仅把输出 model_id 由 postgresql 重命名为 opengauss（不臆造 SQL）。
注：DB 采集器按 dameng 范式置于社区 plugins/inputs；服务端(树/NodeParams/CollectionPlugin)企业化即 OSS 不可触发。
"""
from plugins.inputs.postgresql.postgresql_info import PostgresqlInfo


class OpenGaussInfo(PostgresqlInfo):
    def list_all_resources(self):
        data = super().list_all_resources()
        result = data.get("result", {}) or {}
        if "postgresql" in result:
            recs = result.pop("postgresql")
            for rec in recs:
                if isinstance(rec, dict) and rec.get("inst_name"):
                    rec["inst_name"] = f"{self.host}-opengauss-{self.port}"
            result["opengauss"] = recs
        return data
