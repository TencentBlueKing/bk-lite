"""作业管理工具。文件不作为工具构造参数。"""

import json
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import Field

from apps.opspilot.services.job_tool_service import (
    JobToolError,
    describe_job_script,
    distribute_staged_files,
    list_job_scripts,
    list_job_targets,
    list_playbook_scripts,
    query_job,
    run_custom_script,
    run_library_script,
    schedule_job_watch,
    search_job_targets,
)

JOB_MGMT_PROMPT = """
作业管理只使用当前提问人和当前组织，不能改组织、用户或执行人。没有调用身份就停止，不要提交作业。
脚本库按脚本编号执行，不要索要或复述脚本正文。即使用户没点名、脚本库只有一个，也要用 request_user_choice 确认脚本名称和类型。脚本名称必须出现在当前这句用户原话里，或当前这句选择了「使用脚本 名称」。更早消息里的同名片段不能当作确认。重名时同样让用户选。
选定脚本和目标后先看操作系统。Linux 只能执行 shell 和 python，Windows 只能执行 powershell 和 bat。操作系统未知或不匹配时说明原因，不要提交。
Playbook 只能用 job_mgmt_list_playbook_scripts 按名称或路径查看可选脚本路径。只使用返回的路径，不要索要或复述文件内容。列出路径只用于查看，不表示这些工具能执行 Playbook，也不会提交作业。job_mgmt_run_library 和 job_mgmt_run_custom 只执行作业脚本（脚本库脚本和自定义脚本），不能执行 Playbook。
每个参数单独问使用默认值还是自己填写。必填且没有默认值的必须填写。加密默认值保持 ******。枚举只能选已有选项。
自定义脚本只接受 shell、python、powershell、bat。类型和正文必须出现在同一句用户原话里，可以是本会话较早的一句。不要代写或改写，也不要编指定句式让用户重说。选定目标后直接执行。
目标先按名称或 IP 查询。用户已经说了节点管理或作业管理目标时，只在这个来源里找，不要把另一个来源放进选项。
唯一命中直接用。多个命中只在这些结果里用 request_user_choice。用户还没说来源且一台都没有时，再让用户选来源。
用户消息里已经有 (node_mgmt:编号) 或 (manual:编号) 时，直接用括号里的编号执行，不要再搜索，不要再问是不是节点管理。
执行和分发的 target_ids 只填查询结果里的 id：作业管理目标是数字 id，节点管理目标是节点主键。不要填 IP，不要填名称。
同一未结束作业再次执行时沿用原作业号，不要重新提交。失败、取消或执行超时后，必须等用户说出「确认重跑」才能再提交。
脚本结果里的标准输出和标准错误只出现在对话展示块，不要写进回复。output_shown 为 true 时，输出已经展示，不要再叫用户去别处查看。
output_shown 为 false 时，5 分钟内没有脚本输出。说明作业号、status、waited_seconds，并把 result_url 原样写成 markdown 链接。不要改地址，也不要只说去作业管理看。然后再问要不要「定时检查」，不要重新提交。
文件分发只用本会话暂存文件。目标路径必须是当前这句里的完整路径，或与某一句用户原话整句相同。不要把更长路径截成父目录，也不要沿用无关历史里的路径。覆盖或跳过必须写在当前这句，不要沿用更早的选择，不要默认覆盖。
问覆盖或跳过只是因为用户还没选策略，分发前不会检查目标磁盘。不要说目标上已经有这个文件，也不要说被同名文件阻塞。
终态只说成功或失败。返回里有 result_url 时作业还在执行，不要说失败。
告诉用户到作业管理查看任务状态，说明作业号和 waited_seconds，并把 result_url 原样写成 markdown 链接。
高危确认只能等用户说出「确认执行」。禁止级直接拒绝。
""".strip()


def _run(func):
    try:
        return func()
    except JobToolError as exc:
        return {"result": False, "message": exc.message}


_TARGET_SOURCE = Annotated[
    str,
    Field(description="只能填「作业管理目标」或「节点管理目标」。对应查询结果的 source：manual 用作业管理目标，node_mgmt 用节点管理目标。"),
]
_TARGET_IDS = Annotated[
    str,
    Field(description=("查询结果条目的 id，多个用英文逗号连接。" "作业管理目标的 id 是数字；节点管理目标的 id 是节点主键。" "不要填 ip，不要填 name，不要填 JSON 数组。")),
]


def _loads(raw, default):
    if raw in (None, ""):
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


@tool(description="列出当前组织的脚本库脚本。只返回编号、名称、类型和参数定义，没有脚本正文。即使只有一个，也要用 request_user_choice 让用户确认名称和类型。")
def job_mgmt_list_scripts(name: str = "", config: RunnableConfig = None):
    return _run(lambda: list_job_scripts(config, name))


@tool(
    description=(
        "按 Playbook 名称或包内路径列出当前组织可选的 Playbook 脚本路径。"
        "只返回编号、名称、版本、路径和参数定义，没有文件内容。"
        "多条路径用 request_user_choice 让用户选。"
        "列出路径不表示可以执行 Playbook。这些作业工具不能跑 Playbook，"
        "job_mgmt_run_library 和 job_mgmt_run_custom 只执行作业脚本。这个工具只查看，不提交作业。"
    )
)
def job_mgmt_list_playbook_scripts(name: str = "", path: str = "", config: RunnableConfig = None):
    return _run(lambda: list_playbook_scripts(config, name, path))


@tool(description="查看一个脚本的参数定义。加密默认值是 ******。不要据此复述脚本正文。")
def job_mgmt_describe_script(script_id: int, config: RunnableConfig = None):
    return _run(lambda: describe_job_script(config, script_id))


@tool(
    description=(
        "按名称或 IP 查找目标。用户说过节点管理或作业管理目标时，结果里只有这个来源。"
        "返回 use 时直接执行，不要再问来源。用户消息里已有 (node_mgmt:编号) 或 (manual:编号) 时，用括号里的编号，不要再搜。"
        "多个命中才用 request_user_choice。用户还没说来源且零命中时，才让用户选来源。"
    )
)
def job_mgmt_search_targets(keyword: str, config: RunnableConfig = None):
    return _run(lambda: search_job_targets(config, keyword))


@tool(description="在用户选定的来源里分页列出目标。每条含 id、name、ip、os。执行时 target_ids 只复制 id。source 填作业管理目标或节点管理目标。下一页把上次返回的 next_cursor 填进参数 cursor。")
def job_mgmt_list_targets(
    source: Annotated[str, Field(description="作业管理目标或节点管理目标")],
    cursor: Annotated[str, Field(description="上一页返回的 next_cursor。第一页留空。参数名是 cursor，不是 next_cursor。")] = "",
    config: RunnableConfig = None,
):
    return _run(lambda: list_job_targets(config, source, cursor))


@tool(
    description=(
        '按脚本编号执行当前组织的脚本库脚本。params_json 是 [{"name","use_default","value"}]，每个参数都要有。'
        "use_default 为 true 时不要填写加密真值。危险规则需要确认时，等用户说出确认执行后再把 danger_confirmed 设为 true。"
        "当前这句用户原话里没有脚本名称，且没有选择「使用脚本 名称」时，先让用户确认，不要执行。更早消息里出现过名称不算确认。"
        "目标系统不支持该脚本类型时不会创建作业。"
        "target_ids 填查询结果的 id，不填 IP。有脚本输出时只返回作业号和终态；没有输出时附带 result_url，原样作为链接给用户。"
    )
)
def job_mgmt_run_library(
    script_id: Annotated[int, Field(description="job_mgmt_list_scripts 返回的数字 id")],
    target_source: _TARGET_SOURCE,
    target_ids: _TARGET_IDS,
    params_json: Annotated[str, Field(description='JSON 数组字符串，形如 [{"name","use_default","value"}]。每个参数都要有。use_default 为 true 时不要填加密真值。')] = "",
    danger_confirmed: Annotated[bool, Field(description="只有用户原话包含「确认执行」才能为 true")] = False,
    confirmed_rerun: Annotated[bool, Field(description="只有用户原话包含「确认重跑」或「重新执行」才能为 true")] = False,
    name: Annotated[str, Field(description="作业名称。用户没起名就留空，服务端用脚本名。")] = "",
    config: RunnableConfig = None,
):
    return _run(
        lambda: run_library_script(
            config,
            script_id=script_id,
            target_source=target_source,
            target_ids=target_ids,
            params=_loads(params_json, []),
            danger_confirmed=danger_confirmed,
            confirmed_rerun=confirmed_rerun,
            name=name,
        )
    )


@tool(
    description=(
        "执行用户在本会话里已经写明类型和正文的自定义脚本。类型只能是 shell、python、powershell、bat。"
        "类型和正文要在同一句用户原话里，可以是较早的一句。不要修改，选定目标后不要让用户重说。"
        "Linux 只能执行 shell 和 python，Windows 只能执行 powershell 和 bat。"
        "target_ids 填查询结果的 id，不填 IP。操作系统不匹配时不会创建作业。有脚本输出时只返回作业号和终态；没有输出时附带 result_url，原样作为链接给用户。"
    )
)
def job_mgmt_run_custom(
    script_type: Annotated[str, Field(description="只能是 shell、python、powershell、bat")],
    script_content: Annotated[str, Field(description="用户原话里的脚本正文，不要改写")],
    target_source: _TARGET_SOURCE,
    target_ids: _TARGET_IDS,
    danger_confirmed: Annotated[bool, Field(description="只有用户原话包含「确认执行」才能为 true")] = False,
    confirmed_rerun: Annotated[bool, Field(description="只有用户原话包含「确认重跑」或「重新执行」才能为 true")] = False,
    name: Annotated[str, Field(description="作业名称。用户没起名就留空。")] = "",
    timeout: Annotated[int, Field(description="超时秒数，默认 600。用户没说超时不要改。")] = 600,
    config: RunnableConfig = None,
):
    return _run(
        lambda: run_custom_script(
            config,
            script_type=script_type,
            script_content=script_content,
            target_source=target_source,
            target_ids=target_ids,
            danger_confirmed=danger_confirmed,
            confirmed_rerun=confirmed_rerun,
            name=name,
            timeout=timeout,
        )
    )


@tool(
    description=(
        "分发当前用户、当前组织、当前会话暂存的文件。"
        "目标路径必须是当前这句里的完整路径，或与某一句用户原话整句相同。不要截成更短的父目录，不要默认覆盖。"
        "覆盖或跳过必须出现在当前这句，更早的选择不算。"
        "问覆盖或跳过不代表已经看到目标上有同名文件。"
        "target_ids 填查询结果的 id，不填 IP。file_ids 为空时按用户提到的文件名匹配。"
        "终态只有成功或失败。作业已提交但还在执行，或提交后查询失败时，返回作业号、仍在执行和 result_url，告诉用户到作业管理查看，不要说成失败。"
    )
)
def job_mgmt_distribute(
    target_source: _TARGET_SOURCE,
    target_ids: _TARGET_IDS,
    target_path: Annotated[str, Field(description="用户原话里的目标目录，不要猜测")] = "",
    file_ids: Annotated[str, Field(description="暂存文件 id，多个用英文逗号连接。留空则按文件名匹配。")] = "",
    danger_confirmed: Annotated[bool, Field(description="只有用户原话包含「确认执行」才能为 true")] = False,
    name: Annotated[str, Field(description="作业名称。用户没起名就留空。")] = "",
    config: RunnableConfig = None,
):
    parsed_ids = [item for item in str(file_ids or "").split(",") if item.strip()]
    return _run(
        lambda: distribute_staged_files(
            config,
            file_ids=parsed_ids,
            target_source=target_source,
            target_ids=target_ids,
            target_path=target_path,
            danger_confirmed=danger_confirmed,
            name=name,
        )
    )


@tool(description="查询本会话已记录的作业号。不要重新提交。脚本只返回作业号和终态。文件终态只返回成功或失败；文件还在执行时返回作业号和 result_url，让用户到作业管理查看。")
def job_mgmt_query(task_id: int = 0, config: RunnableConfig = None):
    return _run(lambda: query_job(config, task_id or None))


@tool(description="用户同意定时检查后，按间隔查看同一个作业号，默认 60 分钟，最长 24 小时。不会重新执行。用户没说定时检查时先用 request_user_choice 询问。")
def job_mgmt_schedule_watch(task_id: int = 0, interval_minutes: int = 60, config: RunnableConfig = None):
    return _run(lambda: schedule_job_watch(config, task_id or None, interval_minutes))
