# language: zh-CN
功能: CMDB 配置采集
  作为 CMDB 资产采集模块
  为了支撑采集任务的调试态机、节点权限校验、调度配置变化检测
  CollectToolService 与 CollectModelService 的工具方法必须严格遵循协议字段与权限规则

  # ---------- Happy Path ----------

  场景: 正常路径 - 调试任务的拥有者从 request.user 抽取 username 与 domain
    假设 一个调试请求由用户 "alice"@"acme.com" 发起
    当 我调用 build_debug_owner
    那么 owner 应当为 {"username":"alice","domain":"acme.com"}

  场景: 正常路径 - 节点权限上下文携带 include_children 与 current_team
    假设 一个调试请求由用户 "alice"@"acme.com" 发起，cookies={"current_team":"7","include_children":"1"}
    当 我调用 build_node_permission_data
    那么 节点权限上下文 include_children 应当为 true
    并且 节点权限上下文 current_team 应当为 "7"

  场景: 正常路径 - 调度参数从 scan_cycle 拆分为 cycle_value 与 is_interval
    假设 一个采集任务请求体 name="抓 host" task_type="host" driver_type="snmp" model_id="host" timeout=30 input_method="manual" scan_cycle_type="cycle" scan_cycle_value="5" team=[1]
    当 我调用 format_params
    那么 格式化结果的 is_interval 应当为 true
    并且 格式化结果的 cycle_value 应当为 "5"
    并且 格式化结果的 cycle_value_type 应当为 "cycle"
    并且 格式化结果的 scan_cycle 应当为 "*/5 * * * *"

  # ---------- Corner Case ----------

  场景: 边界 - owner 不匹配的请求无权访问调试状态
    假设 当前调试状态的 owner 为 {"username":"alice","domain":"acme.com"}
    并且 当前请求来自用户 "bob"@"acme.com"
    当 我调用 can_access_debug_state
    那么 访问决策应当为 false

  场景: 边界 - 未知 debug action 回落到默认 10s 超时
    当 我调用 get_timeout 参数为 "unknown_action"
    那么 超时秒数应当为 10

  场景: 边界 - 已知 debug action 使用 TIMEOUT_MAP 指定值
    当 我调用 get_timeout 参数为 "raw_collect"
    那么 超时秒数应当为 300

  场景: 边界 - 调度配置完全相同时不应被视为变化
    假设 旧任务 is_interval=true cycle_value="*/5 * * * *" cycle_value_type="cycle" scan_cycle="cron"
    并且 新任务 is_interval=true cycle_value="*/5 * * * *" cycle_value_type="cycle" scan_cycle="cron"
    当 我调用 is_schedule_config_changed
    那么 调度变化结果应当为 false

  场景: 边界 - cycle_value 改变时调度被视为变化
    假设 旧任务 is_interval=true cycle_value="*/5 * * * *" cycle_value_type="cycle" scan_cycle="cron"
    并且 新任务 is_interval=true cycle_value="*/10 * * * *" cycle_value_type="cycle" scan_cycle="cron"
    当 我调用 is_schedule_config_changed
    那么 调度变化结果应当为 true

  场景: 边界 - build_error_result 应携带阶段、摘要与目标元数据
    假设 一份采集 payload protocol="snmp" action="raw_collect" target="10.0.0.1" port=161
    当 我以 stage="connect" summary="auth failed" 调用 build_error_result
    那么 错误结果的 success 字段应当为 false
    并且 错误结果的 stage 字段应当为 "connect"
    并且 错误结果的 summary 字段应当为 "auth failed"
    并且 错误结果的 meta.target 字段应当为 "10.0.0.1"
