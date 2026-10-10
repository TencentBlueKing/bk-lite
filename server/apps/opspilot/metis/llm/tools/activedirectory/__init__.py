"""Active Directory 查询工具。

按表查询域中的用户、组、计算机等对象；可查看表结构，并用只读 SQL 检索数据。

工具:
- activedirectory_get_tables
- activedirectory_get_columns
- activedirectory_run_query
"""

from apps.opspilot.metis.llm.tools.activedirectory.tools import activedirectory_get_columns, activedirectory_get_tables, activedirectory_run_query

CONSTRUCTOR_PARAMS = [
    {"name": "ad_instances", "type": "string", "required": False, "description": "Active Directory 多实例 JSON 配置"},
    {"name": "ad_default_instance_id", "type": "string", "required": False, "description": "默认 AD 实例 ID"},
]

__all__ = [
    "CONSTRUCTOR_PARAMS",
    "activedirectory_get_tables",
    "activedirectory_get_columns",
    "activedirectory_run_query",
]
