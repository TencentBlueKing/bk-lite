"""把流程校验错误译成当前账号语言的整句，名字用界面上的节点名和字段名。"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from apps.workflow.services.definitions import DefinitionValidationError
from apps.workflow.utils.i18n import _normalize_locale, get_workflow_loader, workflow_message

_STATIC_CODES = {
    "Conductor DSL 必须是 JSON 对象": "definition_not_object",
    "canvas_metadata 必须是 JSON 对象": "canvas_not_object",
    "disabled_nodes 必须是节点引用数组": "disabled_nodes_not_array",
    "单个流程最多停用 100 个节点": "disabled_nodes_limit",
    "disabled_nodes 只能包含非空节点引用": "disabled_nodes_blank",
    "disabled_nodes 不能包含重复节点引用": "disabled_nodes_duplicate",
    "inputs 必须是 JSON 对象": "inputs_not_object",
    "流程输入超过 1 MiB 限额": "inputs_too_large",
    "工作流输入 Schema 非法": "input_schema_invalid",
    "Conductor DSL 必须可序列化为 JSON": "definition_not_json",
    "Conductor DSL 超过 256 KiB 限额": "definition_too_large",
    "Conductor DSL 至少需要一个 tasks 节点": "definition_tasks_required",
    "单个流程最多支持 100 个节点": "node_limit",
    "控制结构嵌套深度最多为 5": "nesting_limit",
    "tasks 中的节点必须是对象": "task_not_object",
    "每个节点必须包含 name 和 taskReferenceName": "task_identity_required",
    "条件节点的结构化表达式非法": "condition_expression_invalid",
    "流程参数契约必须是 JSON 对象": "parameter_contract_not_object",
    "不支持的流程参数契约版本": "parameter_contract_version",
    "流程常量和流程输出已移除，请使用设置数据和对应的 Return 节点": "legacy_contract_removed",
    "流程必须包含 1 到 10 个触发节点": "trigger_count",
    "触发节点 ID 缺失、重复或非法": "trigger_id_invalid",
    "Return 节点 ID 缺失、重复或非法": "return_id_invalid",
    "画布连线引用了不存在的节点或自环": "edge_invalid",
    "触发节点不能有入边": "trigger_incoming_edge",
    "Return 节点不能有出边": "return_outgoing_edge",
    "流程画布不能包含环": "graph_cycle",
    "等待模式 Webhook 触发路径必须且只能到达一个 Webhook 响应节点": "webhook_wait_return",
    "流程定义和画布元数据必须是 JSON 对象": "graph_payload_not_object",
    "连线模式不允许手工配置 FORK_JOIN/JOIN": "manual_fork_forbidden",
    "连线模式要求所有业务节点位于画布顶层且引用唯一": "graph_tasks_not_flat",
    "连线模式要求所有触发器进入同一个首节点": "triggers_not_same_entry",
    "触发器 config 必须是 JSON 对象": "trigger_config_not_object",
    "Webhook 响应模式非法": "webhook_response_mode_invalid",
    "该触发类型不需要 config": "trigger_config_forbidden",
    "NATS 触发器不需要配置参数": "nats_trigger_config_forbidden",
    "触发类型非法": "trigger_type_invalid",
    "trigger_nodes 必须是数组": "trigger_nodes_not_array",
    "该触发方式必须提供幂等键": "idempotency_key_required",
    "幂等键最长 128 字符": "idempotency_key_too_long",
    "time 必须包含 1 到 10 个执行时间": "schedule_time_count",
    "time 必须使用 HH:MM 的 24 小时格式": "schedule_time_format",
    "定时触发 config 必须是 JSON 对象": "schedule_config_not_object",
    "frequency 必须是 daily、weekly、monthly 或 crontab": "schedule_frequency_invalid",
    "Cron 表达式非法，必须包含 5 个字段": "cron_field_count",
    "Cron 时区非法": "cron_timezone_invalid",
    "NATS 标准事件信封必须是 JSON 对象": "nats_envelope_not_object",
    "NATS 事件必须包含 event_id、occurred_at、producer 和 payload": "nats_envelope_fields",
    "NATS event_id 必须是非空字符串": "nats_event_id_invalid",
    "NATS occurred_at 必须是非空时间字符串": "nats_occurred_at_invalid",
    "NATS producer 必须是非空字符串": "nats_producer_invalid",
    "NATS payload 必须是 JSON 对象": "nats_payload_not_object",
    "NATS inputs 不是合法 JSON": "nats_inputs_not_json",
    "NATS inputs 最大 1 MiB": "nats_inputs_too_large",
    "NATS 触发请求非法": "nats_request_invalid",
    "NATS 触发参数非法": "nats_arguments_invalid",
    "请先发布流程": "publish_required",
    "流程已停用": "workflow_disabled",
    "流程已删除": "workflow_already_deleted",
    "流程不存在": "workflow_not_found",
    "status 非法": "status_invalid",
    "enabled 非法": "enabled_invalid",
    "trigger_type 非法": "trigger_type_query_invalid",
    "is_builtin 非法": "is_builtin_invalid",
    "enabled 必须是布尔值": "enabled_boolean",
    "当前发布版本不存在": "published_version_missing",
    "当前生效版本不存在": "active_version_missing",
    "内置流程不可保存草稿，请复制后再编辑": "builtin_draft_readonly",
    "内置流程不可删除，可停用或复制后自定义": "builtin_delete_readonly",
    "内置流程不可发布，请复制后再编辑发布": "builtin_publish_readonly",
    "内置流程不可恢复草稿": "builtin_restore_readonly",
    "草稿已经被其他修改更新，请重新载入后再保存": "draft_revision_conflict_save",
    "草稿已经被其他修改更新，请重新载入后再发布": "draft_revision_conflict_publish",
    "草稿已经被其他修改更新，请重新载入后再恢复": "draft_revision_conflict_restore",
    "草稿版本已变化，本次发布已取消": "draft_revision_changed",
    "流程版本已被其他发布占用，请刷新后重试": "publish_version_conflict",
    "流程引用的原子状态或版本已经变化，请刷新后重试": "atom_version_changed",
    "MVP 不支持断点调试": "debug_breakpoint_unsupported",
    "调试触发器不存在": "debug_trigger_missing",
    "请选择要上传的文件": "upload_file_required",
    "知识文件存储暂不可用": "knowledge_store_unavailable",
    "只有已启用的已发布流程可以上传运行模板": "runtime_template_publish_required",
    "流程生效版本已变化，请重新打开执行窗口": "active_version_changed",
    "上传字段不存在或不是文件上传字段": "upload_field_missing",
    "该字段不允许上传文件": "upload_not_allowed",
    "该字段没有配置允许的文件类型": "upload_types_missing",
    "该字段的文件大小配置非法": "upload_size_invalid",
    "报告模板存储暂不可用": "report_store_unavailable",
    "重新执行凭证不能用于流程列表执行": "rerun_token_not_for_list",
    "启动凭证对应的流程版本不存在": "launch_version_missing",
    "当前组织可用原子超过 100 个上限": "atom_catalog_limit",
    "格式非法": "format_invalid",
    "示例模板不存在": "sample_template_missing",
    "source 必须是 node_mgmt 或 job_mgmt": "target_source_invalid",
    "分页参数非法": "page_invalid",
    "节点管理目标暂时不可用": "node_targets_unavailable",
    "作业平台目标暂时不可用": "job_targets_unavailable",
    "values 必须包含 1 到 100 个 IP": "target_values_limit",
    "atom_key 必填": "atom_key_required",
    "node_type 非法": "node_type_invalid",
    "page 或 page_size 非法": "page_size_invalid",
    "page 或 page_size 超出范围": "page_size_range",
    "MVP 原子由研发注册包同步，页面不支持在线创建": "atom_create_unsupported",
    "执行记录只能由流程或触发器创建": "execution_create_unsupported",
    "mode 非法": "mode_invalid",
    "执行节点不存在": "execution_node_missing",
    "当前执行状态不支持该操作": "execution_status_unsupported",
    "执行记录缺少 Conductor Workflow ID": "conductor_id_missing",
    "当前执行已是终态": "execution_already_terminal",
    "终止原因必填": "termination_reason_required",
    "只能重新执行已结束的正式版本": "rerun_terminal_required",
    "原执行对应的流程版本不存在": "rerun_version_missing",
    "启动凭证与原执行不匹配": "launch_token_execution_mismatch",
    "启动凭证与原执行版本不匹配": "launch_token_version_mismatch",
    "触发器必须在流程画布中创建并随版本发布": "trigger_create_unsupported",
    "触发器必须在流程画布中编辑": "trigger_update_unsupported",
    "触发器必须在流程画布中删除": "trigger_delete_unsupported",
    "NATS 触发节点不存在": "nats_trigger_node_missing",
    "NATS 测试会话不属于当前组织": "nats_test_session_team",
    "Webhook 触发节点不存在": "webhook_trigger_node_missing",
    "Webhook 测试会话不属于当前组织": "webhook_test_session_team",
    "流程存在正在运行、等待或取消中的执行，请先终止或等待执行结束": "workflow_delete_active_execution",
    "当前原子下已存在同名配置模板": "config_template_name_exists",
    "模板名称不能为空": "config_template_name_required",
    "不能修改配置模板所属原子": "config_template_atom_immutable",
    "配置模板参数必须是对象": "config_template_params_object",
    "必须在 60 到 86400 秒之间": "idempotency_window_range",
    "触发器必须使用已发布流程的统一输入 Schema": "trigger_input_schema_locked",
    "缺少或非法的 current_team": "invalid_current_team",
    "必须是 JSON 对象": "json_object_required",
    "触发器已停用": "trigger_disabled",
    "只有未删除的已发布流程可以触发": "trigger_workflow_unpublished",
    "流程已删除或未发布，不能创建新执行": "trigger_workflow_unavailable",
    "相同幂等键正在处理": "idempotency_in_progress",
    "NATS 调用方身份非法": "nats_actor_invalid",
    "NATS 触发超出授权组织范围": "nats_team_forbidden",
    "NATS 触发器不存在或不可用": "nats_trigger_unavailable",
    "NATS 消息主题与触发器不匹配": "nats_subject_mismatch",
    "该人工处理项正在提交，请稍后刷新": "interaction_submitting",
    "人工处理项投递令牌已失效": "interaction_token_invalid",
    "该人工处理项已被处理": "interaction_already_decided",
    "该审批已被处理": "approval_already_decided",
    "该人工处理项不是审批": "interaction_not_approval",
    "decision 必须是 APPROVED 或 REJECTED": "decision_invalid",
    "拒绝必须填写意见": "rejection_comment_required",
    "NATS 测试会话已过期，请重新监听": "nats_test_expired",
    "NATS 测试会话非法": "nats_test_invalid",
    "NATS 测试事件最大 1 MiB": "nats_test_too_large",
    "NATS 测试事件必须是合法 JSON": "nats_test_not_json",
    "Webhook 测试会话已过期": "webhook_test_expired",
    "Webhook 测试会话无效": "webhook_test_invalid",
    "Webhook 测试会话不属于调用方组织": "webhook_test_team",
    "Conductor 服务不可用或拒绝了请求": "conductor_unavailable",
    "单节点测试只支持已注册的 SIMPLE 原子": "node_test_simple_only",
    "该原子可能产生真实副作用，单节点测试必须二次确认": "node_test_confirmation_required",
    "node_inputs 必须是 JSON 对象": "node_inputs_object",
    "流程已删除，不能创建新执行": "workflow_deleted",
    "只能执行已发布流程": "workflow_publish_required",
    "流程已删除，不能创建新调试执行": "debug_workflow_deleted",
    "缺少启动凭证，请重新打开执行窗口": "launch_token_missing",
    "启动凭证已过期，请重新打开执行窗口": "launch_token_expired",
    "启动凭证无效，请重新打开执行窗口": "launch_token_invalid",
    "作业平台目标 ID 非法": "job_target_id_invalid",
    "模板超过 5 MiB 限额": "template_too_large",
    "模板解压规模超过安全限额": "template_unzip_limit",
    "模板包含非法文件路径": "template_path_invalid",
    "模板不得包含宏或外部数据连接": "template_macro_forbidden",
    "模板包含异常压缩条目": "template_zip_entry_invalid",
    "模板不得包含外部链接": "template_external_link_forbidden",
    "只支持 docx 或 xlsx 模板": "template_format_unsupported",
    "模板请使用 Jinja 语法 {{ 字段 }} / {% for %}，不支持 Carbone {d.字段}": "template_jinja_required",
    "模板占位符数量超过 200 个": "template_placeholder_limit",
    "模板循环嵌套超过 10 层": "template_loop_depth",
    "模板循环缺少开始标记": "template_loop_start_missing",
    "模板循环数量超过 20 个": "template_loop_count",
    "Word 模板渲染返回了空文档": "word_render_empty",
    "Excel 模板渲染返回了空文档": "excel_render_empty",
    "文档数据必须是 JSON 对象": "document_data_object",
    "邮件通知必须选择收件人": "email_recipients_required",
    "报告文件引用非法": "report_reference_invalid",
    "报告文件不存在或无权访问": "report_reference_forbidden",
    "报告文件不属于当前执行": "report_reference_execution",
    "recipients 最多支持 100 个收件人": "recipients_limit",
    "通知接收人无效": "recipient_invalid",
    "通知接收人不存在或已失效": "recipient_missing",
    "通知标题或正文超出限额": "notification_text_limit",
    "通知渠道投递失败": "notification_delivery_failed",
    "headers 必须是最多 20 项的对象": "http_headers_object",
    "HTTP Header 必须是有界字符串键值": "http_header_value",
    "HTTP 请求不允许覆盖 Host": "http_host_forbidden",
    "HTTP URL 必填且最长 2000 字符": "http_url_required",
    "HTTP URL 必须是 http(s) 绝对地址": "http_url_absolute",
    "HTTP URL 不得包含用户信息": "http_url_userinfo",
    "额外成功状态码必须是最多 20 项的数组": "http_status_array",
    "成功状态码必须在 100 到 599 之间": "http_status_range",
    "不支持的 HTTP 方法": "http_method_unsupported",
    "HTTP 超时必须在 1 到 60 秒之间": "http_timeout_range",
    "query 必须是最多 50 项的对象": "http_query_object",
    "HTTP 请求体超过 256 KiB 限额": "http_body_limit",
    "HTTP 响应超过 1 MiB 限额": "http_response_limit",
    "HTTP 响应格式非法": "http_response_format",
    "HTTP 响应声明为 JSON 但内容无效": "http_response_json",
    "报告模板快照非法": "template_snapshot_invalid",
    "请上传 Word 或 Excel 报告模板": "template_upload_required",
    "追加文档数据必须是 JSON 对象": "document_extra_object",
    "执行组织与文档组织不一致": "document_team_mismatch",
    "文档格式只能是 docx 或 xlsx": "document_format_invalid",
    "作业执行目标非法": "job_targets_invalid",
    "作业目标缺少受控来源": "job_target_source_missing",
    "作业执行缺少可信流程上下文": "job_context_missing",
    "作业执行缺少可信组织上下文": "job_team_missing",
    "作业执行缺少可信执行人上下文": "job_actor_missing",
    "脚本类型非法": "script_type_invalid",
    "作业执行必须选择 1 到 100 台目标主机": "job_target_count",
    "result= 必须是 JSON 对象": "job_result_object",
    "result= 嵌套超过 10 层": "job_result_depth",
    "result= 后必须是有效 JSON": "job_result_json",
    "执行参数非法": "execution_params_invalid",
    "执行参数超过长度限制": "execution_params_limit",
    "作业脚本不能为空": "script_content_required",
    "文件类型不受支持，请上传 .md 文件": "knowledge_markdown_only",
    "文件超过 10 MiB 限额": "knowledge_file_limit",
    "知识文件必须使用 UTF-8 编码": "knowledge_utf8",
    "知识文件不能为空": "knowledge_empty",
    "流程标识非法": "workflow_id_invalid",
    "知识文件引用非法": "knowledge_reference_invalid",
    "知识文件引用缺少凭证": "knowledge_token_missing",
    "知识文件引用无效": "knowledge_reference_rejected",
    "知识文件引用内容非法": "knowledge_payload_invalid",
    "知识文件总大小超过 20 MiB 限额": "knowledge_total_limit",
    "知识文件内容校验失败": "knowledge_checksum_failed",
    "知识文件内容不是 UTF-8 文本": "knowledge_not_utf8",
    "报告模板引用非法": "report_token_invalid",
    "报告模板引用缺少凭证": "report_token_missing",
    "上传的报告模板已过期，请重新上传": "report_upload_expired",
    "报告模板引用无效": "report_reference_rejected",
    "报告模板引用与当前执行不匹配": "report_execution_mismatch",
    "报告模板引用内容非法": "report_payload_invalid",
    "上传的报告模板已过期，请重新上传后再发布": "report_upload_expired_publish",
    "文档生成节点发布前必须上传 Word 或 Excel 模板": "document_template_required",
    "报告模板内容校验失败": "report_checksum_failed",
    "原子不存在或当前组织无权使用": "config_template_atom_forbidden",
    "配置模板参数不能超过 64 KiB": "config_template_params_limit",
    "指定模型在当前组织不可用": "model_unavailable",
    "指定智能体在当前组织不可用": "agent_unavailable",
    "指定记忆空间在当前组织不可用": "memory_unavailable",
    "OpsPilot 应用未启用": "opspilot_disabled",
    "缺少可信的流程执行上下文": "execution_context_missing",
    "流程执行组织非法": "execution_team_invalid",
    "流程执行身份非法": "execution_actor_invalid",
    "智能体返回结果非法": "agent_result_invalid",
    "intents 必须包含 1 到 20 个意图": "intents_count",
    "intents 不能重复": "intents_duplicate",
    "意图分类返回了未声明的意图": "intent_undeclared",
    "top_k 必须在 1 到 20 之间": "top_k_range",
    "write_batch_size 必须在 1 到 500 之间": "write_batch_range",
    "记忆写入失败": "memory_write_failed",
    "原子缺少执行人快照": "actor_snapshot_missing",
    "原子缺少可信执行上下文": "atom_context_missing",
    "team 必须是单一组织 ID": "team_id_invalid",
    "人工处理项只能由执行引擎产生": "interaction_create_unsupported",
    "同一组织下已存在同名流程": "workflow_name_conflict",
    "请选择组织": "team_required",
    "已发布流程不可修改组织": "published_team_locked",
    "触发器不存在或不属于调用方组织": "trigger_caller_forbidden",
    "缺少流程实例操作权限": "execution_permission_required",
    "编排服务暂不可用": "orchestration_unavailable",
    "原子缺少可信的流程执行上下文": "atom_execution_context_missing",
    "节点输入的 execution_id 与引擎执行实例不一致": "execution_instance_mismatch",
    "当前用户不是该审批的候选人": "approval_candidate_required",
    "启动凭证与当前操作者不匹配": "launch_token_actor_mismatch",
    "启动凭证与当前组织不匹配": "launch_token_team_mismatch",
    "启动凭证与流程不匹配": "launch_token_workflow_mismatch",
    "启动凭证内容非法": "launch_token_payload_invalid",
    "等待 NATS 测试事件超时，请重新监听": "nats_test_timeout",
    "等待 Webhook 测试请求超时": "webhook_test_timeout",
    "作业平台目标校验暂时不可用": "job_target_check_unavailable",
    "节点管理目标校验暂时不可用": "node_target_check_unavailable",
    "Webhook 响应引用的节点未成功完成": "webhook_response_node_incomplete",
    "Webhook 响应引用非法": "webhook_response_reference_invalid",
    "Webhook 响应节点必须选择一个结构化节点输出": "webhook_response_output_required",
    "已发布版本中找不到 Webhook 触发节点": "webhook_published_trigger_missing",
    "流程执行尚未提交到执行引擎": "execution_not_submitted",
    "等待模式必须且只能到达一个 Webhook 响应节点": "webhook_wait_return_required",
    "不支持的作业目标来源": "job_target_source_unsupported",
    "作业取消缺少可信执行人快照": "job_cancel_actor_missing",
    "作业取消缺少组织边界": "job_cancel_team_missing",
    "作业平台取消响应非法": "job_cancel_response_invalid",
    "作业平台巡检任务等待超时": "job_wait_timeout",
    "作业执行缺少可信执行人快照": "job_actor_snapshot_missing",
    "作业目标缺少受控引用 ID": "job_target_reference_missing",
}

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^节点 (?P<node_reference>\S+) 缺少必填输入: (?P<field_list>.+)$"), "node_missing_required_input"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 输入 (?P<field_key>\S+) 不符合原子 Schema: .+$"), "node_input_invalid"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 的字面量不符合目标 Schema: .+$"), "node_literal_invalid"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 引用了当前路径不保证可用的输出: (?P<source>.+)$"), "output_not_reachable"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 的引用类型 (?P<source_type>\S+) 不能绑定到 (?P<target_type>\S+)$"), "reference_type_mismatch"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 的目标字段不允许接收敏感值$"), "sensitive_target_forbidden"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 只能在 string 字段使用文本模板$"), "template_string_only"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 的文本模板不能使用敏感值$"), "template_sensitive_forbidden"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 的文本模板不能使用可为 null 的值$"), "template_null_forbidden"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 的对象字段缺少必填属性: (?P<field_key>\S+)$"), "object_property_required"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 的未声明对象属性 (?P<field_key>\S+) 不能接收敏感值$"), "undeclared_sensitive_property"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 的未声明字段 (?P<field_key>\S+) 不能接收敏感值$"), "undeclared_sensitive_field"),
    (re.compile(r"^流程输入不符合 Schema: (?P<location>\S+): .+$"), "workflow_input_schema_mismatch"),
    (re.compile(r"^停用节点不存在: (?P<names>.+)$"), "disabled_nodes_missing"),
    (re.compile(r"^只有 SIMPLE 原子节点可以停用: (?P<names>.+)$"), "disabled_nodes_not_simple"),
    (re.compile(r"^停用节点 (?P<node_reference>\S+) 的输出仍被引用，请先调整下游配置$"), "disabled_node_output_referenced"),
    (re.compile(r"^审批节点 (?P<node_reference>\S+) 必须紧接包含 true/false 的决策分支$"), "approval_decision_required"),
    (re.compile(r"^审批节点 (?P<node_reference>\S+) 启用超时后必须连接 timeout 分支$"), "approval_timeout_branch_required"),
    (re.compile(r"^审批节点 (?P<node_reference>\S+) 必须配置 1 到 20 个不重复候选审批人$"), "approval_candidates"),
    (re.compile(r"^审批节点 (?P<node_reference>\S+) 必须配置标题$"), "approval_title_required"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 必须填写节点名称$"), "node_title_required"),
    (re.compile(r"^条件节点 (?P<node_reference>\S+) 必须使用结构化条件，不支持自由表达式$"), "condition_free_expression"),
    (re.compile(r"^条件节点 (?P<node_reference>\S+) 必须使用结构化条件$"), "condition_structured_required"),
    (re.compile(r"^条件节点 (?P<node_reference>\S+) 不能混用 ALL/ANY 规则$"), "condition_mixed_rules"),
    (re.compile(r"^条件节点 (?P<node_reference>\S+) 的结构化规则序号非法$"), "condition_rule_index_invalid"),
    (re.compile(r"^条件节点 (?P<node_reference>\S+) 的结构化参数非法$"), "condition_params_invalid"),
    (re.compile(r"^条件节点 (?P<node_reference>\S+) 左值必须是数据引用$"), "condition_left_reference"),
    (re.compile(r"^条件节点 (?P<node_reference>\S+) 的大小比较只支持数值类型$"), "condition_numeric_only"),
    (re.compile(r"^条件节点 (?P<node_reference>\S+) 的包含操作只支持字符串或数组$"), "condition_contains_type"),
    (re.compile(r"^条件节点 (?P<node_reference>\S+) 的开头/结尾操作只支持字符串$"), "condition_affix_type"),
    (re.compile(r"^条件节点 (?P<node_reference>\S+) 必须包含 1 到 10 个分支$"), "condition_branch_count"),
    (re.compile(r"^并行节点 (?P<node_reference>\S+) 必须包含 2 到 10 个非空分支$"), "parallel_branch_count"),
    (re.compile(r"^汇聚节点 (?P<node_reference>\S+) 必须配置 joinOn$"), "join_on_required"),
    (re.compile(r"^节点引用重复: (?P<node_reference>\S+)$"), "duplicate_reference"),
    (re.compile(r"^不支持的原子: (?P<name>.+)$"), "unsupported_atom"),
    (re.compile(r"^不支持的 Conductor 节点类型: (?P<task_type>\S+)$"), "unsupported_task_type"),
    (re.compile(r"^数据引用不存在: (?P<expression>.+)$"), "reference_missing"),
    (re.compile(r"^敏感值不能用于控制流、审批或等待节点: (?P<node_reference>\S+)$"), "sensitive_control_flow"),
    (re.compile(r"^敏感流程输入 (?P<field_key>\S+) 必须使用 string 类型$"), "sensitive_input_string"),
    (re.compile(r"^敏感流程输入 (?P<field_key>\S+) 不能配置默认值$"), "sensitive_input_default"),
    (re.compile(r"^敏感流程输入 (?P<field_key>\S+) 必须是字符串$"), "sensitive_input_runtime_string"),
    (re.compile(r"^流程输入 (?P<field_key>\S+) 的分组非法$"), "input_group_invalid"),
    (re.compile(r"^流程输入 (?P<field_key>\S+) 的默认值不符合 Schema$"), "input_default_invalid"),
    (re.compile(r"^参数 key 不能使用保留前缀: (?P<name>\S+)$"), "parameter_key_reserved"),
    (re.compile(r"^参数 key 重复: (?P<name>\S+)$"), "parameter_key_duplicate"),
    (re.compile(r"^参数 (?P<field_key>\S+) 缺少 Schema$"), "parameter_schema_missing"),
    (re.compile(r"^参数 (?P<field_key>\S+) 的 Schema 非法$"), "parameter_schema_invalid"),
    (re.compile(r"^流程参数契约 (?P<collection>\S+) 必须是数组$"), "parameter_collection_array"),
    (re.compile(r"^(?P<collection>\S+)\[(?P<index>\d+)\] 必须是对象$"), "parameter_item_object"),
    (re.compile(r"^(?P<collection>\S+)\[(?P<index>\d+)\] 的 parameterId 缺失或重复$"), "parameter_id_invalid"),
    (re.compile(r"^(?P<collection>\S+)\[(?P<index>\d+)\] 的 key 非法$"), "parameter_item_key_invalid"),
    (re.compile(r"^资源选择字段 (?P<field_key>\S+) 缺少运行时目标配置$"), "resource_config_missing"),
    (re.compile(r"^资源选择字段 (?P<field_key>\S+) 的目标来源非法$"), "resource_source_invalid"),
    (re.compile(r"^资源选择字段 (?P<field_key>\S+) 的操作系统约束非法$"), "resource_os_invalid"),
    (re.compile(r"^资源选择字段 (?P<field_key>\S+) 的数量约束非法$"), "resource_count_invalid"),
    (re.compile(r"^资源选择字段 (?P<field_key>\S+) 的 Schema 与数量约束不一致$"), "resource_schema_mismatch"),
    (re.compile(r"^文件字段 (?P<field_key>\S+) 缺少上传配置$"), "file_config_missing"),
    (re.compile(r"^文件字段 (?P<field_key>\S+) 的文件类型非法$"), "file_type_invalid"),
    (re.compile(r"^文件字段 (?P<field_key>\S+) 的来源非法$"), "file_source_invalid"),
    (re.compile(r"^文件字段 (?P<field_key>\S+) 的上传限额非法$"), "file_limit_invalid"),
    (re.compile(r"^文件字段 (?P<field_key>\S+) 的 Schema 与文件来源不一致$"), "file_source_mismatch"),
    (re.compile(r"^文件字段 (?P<field_key>\S+) 的 Schema 与文件类型不一致$"), "file_type_mismatch"),
    (re.compile(r"^文件字段 (?P<field_key>\S+) 的 Schema 与上传限额不一致$"), "file_limit_mismatch"),
    (re.compile(r"^(?P<field_key>\S+) 必须是对象数组$"), "object_array_required"),
    (re.compile(r"^触发节点 (?P<node_reference>\S+) 的 input_schema 必须是对象$"), "trigger_schema_object"),
    (re.compile(r"^触发节点 (?P<node_reference>\S+) 的 input_schema 非法$"), "trigger_schema_invalid"),
    (re.compile(r"^触发节点 (?P<node_reference>\S+) 的 input_schema 顶层必须是 object$"), "trigger_schema_root"),
    (re.compile(r"^触发节点 (?P<node_reference>\S+) 类型非法$"), "trigger_node_type_invalid"),
    (re.compile(r"^触发节点 (?P<node_reference>\S+) 最多定义 50 个输入字段$"), "trigger_field_limit"),
    (re.compile(r"^触发节点 (?P<node_reference>\S+) 的 required 引用了不存在的字段$"), "trigger_required_unknown"),
    (re.compile(r"^触发节点 (?P<node_reference>\S+) 的输入 key 非法$"), "trigger_field_key_invalid"),
    (re.compile(r"^触发节点 (?P<node_reference>\S+) 的 config 必须是对象$"), "trigger_node_config_object"),
    (re.compile(r"^Webhook 触发节点 (?P<node_reference>\S+) 响应模式非法$"), "webhook_node_response_mode"),
    (re.compile(r"^NATS 触发节点 (?P<node_reference>\S+) 不需要配置参数$"), "nats_node_config_forbidden"),
    (re.compile(r"^Return 节点 (?P<node_reference>\S+) 类型非法$"), "return_node_type_invalid"),
    (re.compile(r"^Return 节点 (?P<node_reference>\S+) 的 config 必须是对象$"), "return_node_config_object"),
    (re.compile(r"^Webhook 响应节点 (?P<node_reference>\S+) 必须选择一个完整结构化输出$"), "webhook_return_output_required"),
    (re.compile(r"^(?P<trigger_type>\S+) 触发路径禁止出现 Return$"), "trigger_return_forbidden"),
    (re.compile(r"^(?P<trigger_type>\S+) 触发路径必须到达对应 Return$"), "trigger_return_required"),
    (re.compile(r"^(?P<trigger_type>\S+) 触发路径只能到达 (?P<return_type>\S+) Return$"), "trigger_return_type"),
    (re.compile(r"^(?P<trigger_type>\S+) 触发路径存在未连接到 Return 的结束节点$"), "trigger_return_dangling"),
    (re.compile(r"^存在未连接到任何触发器的节点: (?P<names>.+)$"), "orphan_nodes"),
    (re.compile(r"^画布分支不是可结构化的 DAG，节点 (?P<node_reference>\S+) 被多条路径重复进入$"), "graph_reentry"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 只有条件分支可以同时连接响应节点和后续任务$"), "graph_mixed_successors"),
    (re.compile(r"^节点 (?P<node_reference>\S+) 存在空分支$"), "graph_empty_branch"),
    (re.compile(r"^画布存在无法编译的节点: (?P<names>.+)$"), "graph_uncompiled"),
    (re.compile(r"^(?P<field_key>[A-Za-z_][A-Za-z0-9_]*) 必须至少选择一项$"), "schedule_selection_required"),
    (re.compile(r"^(?P<field_key>[A-Za-z_][A-Za-z0-9_]*) 选择项过多$"), "schedule_selection_limit"),
    (re.compile(r"^(?P<field_key>[A-Za-z_][A-Za-z0-9_]*) 必须是 (?P<minimum>\d+) 到 (?P<maximum>\d+) 的整数$"), "schedule_integer_range"),
    (re.compile(r"^不支持的目标来源: (?P<name>\S+)$"), "target_source_unsupported"),
    (re.compile(r"^非法目标引用: (?P<name>.+)$"), "target_reference_invalid"),
    (re.compile(r"^目标来源不允许: (?P<name>.+)$"), "target_source_forbidden"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 必须是数组$"), "target_field_array"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 不能包含重复目标$"), "target_field_duplicate"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 必须选择 (?P<minimum>\d+) 到 (?P<maximum>\d+) 台主机$"), "target_field_count"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 的允许来源非法$"), "target_field_source_invalid"),
    (re.compile(r"^所有目标字段去重后的总数不能超过 (?P<count>\d+) 台$"), "target_total_limit"),
    (re.compile(r"^目标不存在或无权访问: (?P<names>.+)$"), "target_not_found"),
    (re.compile(r"^跨来源目标身份冲突: (?P<left>\S+) 与 (?P<right>\S+)$"), "target_identity_conflict"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 包含不支持的操作系统: (?P<names>.+)$"), "target_os_unsupported"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 必须是字符串数组$"), "launch_target_array"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 不能标记为敏感$"), "launch_target_sensitive"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 缺少允许来源$"), "launch_target_source_missing"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 包含不支持的来源$"), "launch_target_source_unsupported"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 的操作系统约束非法$"), "launch_target_os_invalid"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 包含不支持的操作系统$"), "launch_target_os_unsupported"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 的数量约束非法$"), "launch_target_count_invalid"),
    (re.compile(r"^目标字段 (?P<field_key>\S+) 的 Schema 与选择器数量约束不一致$"), "launch_target_schema_mismatch"),
    (re.compile(r"^(?P<count>\d+) 台主机当前离线，需要二次确认$"), "offline_confirmation_required"),
    (re.compile(r"^(?P<fmt>\S+) 不是有效的 Office Open XML 文件$"), "template_ooxml_invalid"),
    (re.compile(r"^模板不得引用敏感字段: (?P<path>.+)$"), "template_sensitive_path"),
    (re.compile(r"^模板循环语法错误: (?P<raw>.+)$"), "template_loop_syntax"),
    (re.compile(r"^模板循环变量非法: (?P<name>\S+)$"), "template_loop_variable"),
    (re.compile(r"^模板循环缺少结束标记: (?P<name>.+)$"), "template_loop_end_missing"),
    (re.compile(r"^Word 模板渲染失败: (?P<detail>.+)$"), "word_render_failed"),
    (re.compile(r"^Excel 模板渲染失败: (?P<detail>.+)$"), "excel_render_failed"),
    (re.compile(r"^HTTP 响应状态码 (?P<status_code>\d+) 不在成功范围内$"), "http_status_rejected"),
    (re.compile(r"^文件类型不受支持，请上传 (?P<names>.+)$"), "upload_type_unsupported"),
    (re.compile(r"^文件超过 (?P<count>\d+) MiB 限额$"), "upload_size_limit"),
    (re.compile(r"^知识文件必须是 1 到 (?P<count>\d+) 个受控上传引用$"), "knowledge_reference_count"),
    (re.compile(r"^智能体执行失败: (?P<detail>.+)$"), "agent_execution_failed"),
    (re.compile(r"^意图分类失败: (?P<detail>.+)$"), "intent_execution_failed"),
    (re.compile(r"^(?P<label>.+)必须是字符串$"), "text_field_string"),
    (re.compile(r"^(?P<label>.+)超出限额$"), "text_field_limit"),
    (re.compile(r"^节点 (?P<node_reference>\S+) (?P<detail>.+)$"), "node_detail"),
]


def _walk_tasks(tasks: Any, found: list[dict[str, Any]]) -> None:
    if not isinstance(tasks, list):
        return
    for task in tasks:
        if not isinstance(task, dict):
            continue
        found.append(task)
        for branch in task.get("forkTasks") or []:
            _walk_tasks(branch, found)
        for branch in (task.get("decisionCases") or {}).values():
            _walk_tasks(branch, found)
        _walk_tasks(task.get("defaultCase"), found)


class _DisplayNames:
    def __init__(self, request: Any, definition: Any, metadata: Any, atom_catalog: dict[str, Any]) -> None:
        self.request = request
        self.loader = get_workflow_loader(request)
        self.atom_catalog = atom_catalog
        self.metadata = metadata if isinstance(metadata, dict) else {}
        self.tasks = []
        if isinstance(definition, dict):
            _walk_tasks(definition.get("tasks"), self.tasks)
        self.labels = self._build_labels()

    def _text(self, key: str) -> str:
        value = self.loader.get(key)
        return value if isinstance(value, str) else ""

    def _atom_name(self, atom_key: str) -> str:
        localized = self._text(f"atom_name.{atom_key}")
        if localized:
            return localized
        catalog_item = self.atom_catalog.get(atom_key) or {}
        name = catalog_item.get("name")
        return str(name) if name else ""

    def _base_label(self, reference: str) -> str:
        custom = (self.metadata.get("node_titles") or {}).get(reference)
        if isinstance(custom, str) and custom.strip():
            return custom.strip()
        for trigger in self.metadata.get("trigger_nodes") or []:
            if isinstance(trigger, dict) and trigger.get("id") == reference:
                name = trigger.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
                return self._text(f"node_name.{trigger.get('trigger_type')}") or reference
        for item in self.metadata.get("return_nodes") or []:
            if isinstance(item, dict) and item.get("id") == reference:
                name = item.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
                return self._text(f"node_name.{item.get('return_type')}_RETURN") or reference
        task = next((item for item in self.tasks if item.get("taskReferenceName") == reference), None)
        if task is None:
            return reference
        atom_key = str(task.get("name") or "")
        return self._atom_name(atom_key) or self._text(f"node_name.{atom_key}") or reference

    def _build_labels(self) -> dict[str, str]:
        references = [str(task.get("taskReferenceName")) for task in self.tasks if task.get("taskReferenceName")]
        for collection in ("trigger_nodes", "return_nodes"):
            for item in self.metadata.get(collection) or []:
                if isinstance(item, dict) and item.get("id"):
                    references.append(str(item["id"]))
        bases = {reference: self._base_label(reference) for reference in references}
        counts = Counter(bases.values())
        return {reference: base if counts[base] == 1 else f"{base} · {reference}" for reference, base in bases.items()}

    def node_label(self, reference: str) -> str:
        return self.labels.get(reference) or self._base_label(reference)

    def atom_key(self, reference: str) -> str:
        task = next((item for item in self.tasks if item.get("taskReferenceName") == reference), None)
        return str((task or {}).get("name") or "")

    def field_label(self, atom_key: str, field_key: str) -> str:
        override = self._text(f"field_label.{atom_key}.{field_key}")
        if override:
            return override
        catalog_item = self.atom_catalog.get(atom_key) or {}
        properties = (catalog_item.get("input_schema") or {}).get("properties") or {}
        title = properties.get(field_key, {}).get("title") if isinstance(properties, dict) else None
        if isinstance(title, str) and title.strip():
            return title.strip()
        return field_key


def _classify_message(message: str) -> tuple[str, dict[str, Any]]:
    static = _STATIC_CODES.get(message)
    if static:
        return static, {}
    for pattern, code in _PATTERNS:
        matched = pattern.fullmatch(message)
        if matched:
            return code, matched.groupdict()
    return "", {}


def _classify(error: DefinitionValidationError) -> tuple[str, dict[str, Any]]:
    if error.code:
        return error.code, dict(error.params)
    return _classify_message(str(error))


def _format_classified(
    request: Any,
    code: str,
    params: dict[str, Any],
    fallback: str,
    *,
    definition: Any = None,
    metadata: Any = None,
    atom_catalog: dict[str, Any] | None = None,
) -> str:
    names = _DisplayNames(request, definition, metadata, atom_catalog or {})
    node_reference = str(params.get("node_reference") or "")
    atom_key = str(params.get("atom_key") or (names.atom_key(node_reference) if node_reference else ""))
    values: dict[str, Any] = {key: value for key, value in params.items() if key not in {"field_keys", "atom_key"} and isinstance(value, (str, int))}
    if node_reference:
        values["node"] = names.node_label(node_reference)
        values["node_reference"] = node_reference
    field_keys = params.get("field_keys")
    if field_keys is None and params.get("field_list"):
        field_keys = [item.strip() for item in str(params["field_list"]).split(",") if item.strip()]
    if isinstance(field_keys, list):
        locale = _normalize_locale(getattr(getattr(request, "user", None), "locale", None))
        joiner = "、" if locale == "zh-Hans" else ", "
        values["fields"] = joiner.join(names.field_label(atom_key, str(item)) for item in field_keys)
    if params.get("field_key"):
        values["field"] = names.field_label(atom_key, str(params["field_key"]))
    return workflow_message(request, f"error.{code}", fallback, **values)


def render_known_message(
    request: Any,
    message: str,
    *,
    definition: Any = None,
    metadata: Any = None,
    atom_catalog: dict[str, Any] | None = None,
) -> str:
    """把一条已知的中文技术句子换成当前账号语言。没有词条时原样返回。"""
    code, params = _classify_message(message)
    if not code:
        return message
    return _format_classified(
        request,
        code,
        params,
        message,
        definition=definition,
        metadata=metadata,
        atom_catalog=atom_catalog,
    )


def render_workflow_error(
    request: Any,
    error: BaseException,
    *,
    definition: Any = None,
    metadata: Any = None,
    atom_catalog: dict[str, Any] | None = None,
) -> str:
    """用户可见的整句。校验错误优先用显式错误码，其余按稳定中文句子匹配。"""
    if isinstance(error, DefinitionValidationError) and error.code:
        code, params = error.code, dict(error.params)
    else:
        code, params = _classify_message(str(error))
    if not code:
        return str(error)
    return _format_classified(
        request,
        code,
        params,
        str(error),
        definition=definition,
        metadata=metadata,
        atom_catalog=atom_catalog,
    )


def render_definition_error(
    request: Any,
    error: BaseException,
    *,
    definition: Any = None,
    metadata: Any = None,
    atom_catalog: dict[str, Any] | None = None,
) -> str:
    """用户可见的校验句。没有对应文案时保留原始技术句子。"""
    return render_workflow_error(
        request,
        error,
        definition=definition,
        metadata=metadata,
        atom_catalog=atom_catalog,
    )
