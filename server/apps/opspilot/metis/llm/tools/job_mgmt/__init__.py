"""作业管理内置工具。

用当前用户和当前组织执行脚本库脚本、四种自定义脚本，并分发本会话暂存文件。
列出 Playbook 路径只用于查看，这些工具不能执行 Playbook。
脚本输出只展示给用户。模型只看作业号和终态。文件分发的终态只看成功或失败；还在执行或提交后查询失败时给出作业记录链接。
"""

from apps.opspilot.metis.llm.tools.job_mgmt.tools import (
    job_mgmt_describe_script,
    job_mgmt_distribute,
    job_mgmt_list_playbook_scripts,
    job_mgmt_list_scripts,
    job_mgmt_list_targets,
    job_mgmt_query,
    job_mgmt_run_custom,
    job_mgmt_run_library,
    job_mgmt_schedule_watch,
    job_mgmt_search_targets,
)
from apps.opspilot.utils.db_cleanup import wrap_langchain_tool

_JOB_TOOLS = (
    job_mgmt_list_scripts,
    job_mgmt_list_playbook_scripts,
    job_mgmt_describe_script,
    job_mgmt_search_targets,
    job_mgmt_list_targets,
    job_mgmt_run_library,
    job_mgmt_run_custom,
    job_mgmt_distribute,
    job_mgmt_query,
    job_mgmt_schedule_watch,
)
for _tool in _JOB_TOOLS:
    wrap_langchain_tool(_tool)
del _tool, _JOB_TOOLS

CONSTRUCTOR_PARAMS = []

__all__ = [
    "CONSTRUCTOR_PARAMS",
    "job_mgmt_list_scripts",
    "job_mgmt_list_playbook_scripts",
    "job_mgmt_describe_script",
    "job_mgmt_search_targets",
    "job_mgmt_list_targets",
    "job_mgmt_run_library",
    "job_mgmt_run_custom",
    "job_mgmt_distribute",
    "job_mgmt_query",
    "job_mgmt_schedule_watch",
]
