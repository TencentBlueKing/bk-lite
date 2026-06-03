# language: zh-CN
功能: CMDB 采集任务调试状态机
  作为采集任务调试用户
  为了在采集执行前预演协议连通性
  CollectToolService 必须按 submit → running → success 维护 debug 状态机，并强制 owner 鉴权

  # ---------- Happy Path ----------

  场景: 正常路径 - submit 阶段保存 debug 状态并能回读
    当 我以 owner={"username":"alice","domain":"acme.com"} 保存 debug 状态 status="submitted"
    那么 回读的 debug 状态 status 应当为 "submitted"
    并且 回读的 debug 状态 owner.username 应当为 "alice"

  场景: 正常路径 - running → success 状态流转保留原有 owner
    假设 已存在 debug 状态 owner={"username":"alice","domain":"acme.com"} status="running"
    当 我以 result={"ok":true} 保存 debug 状态 status="success"
    那么 回读的 debug 状态 status 应当为 "success"
    并且 回读的 debug 状态 owner.username 应当为 "alice"
    并且 回读的 debug 状态 result.ok 应当为 true

  场景: 正常路径 - build_submit_response 携带 debug_id 与轮询间隔
    当 我构造 submit_response debug_id="dbg_1" status="submitted"
    那么 响应的 debug_id 应当为 "dbg_1"
    并且 响应的 status 应当为 "submitted"
    并且 响应应当包含字段 "poll_interval_ms"

  # ---------- Corner Case ----------

  场景: 边界 - 未存在的 debug_id 回读返回 None
    当 我读取 debug 状态 debug_id="dbg_missing"
    那么 回读结果应当为空

  场景: 边界 - 不匹配 owner 的请求无权访问调试状态
    假设 已存在 debug 状态 owner={"username":"alice","domain":"acme.com"} status="running"
    当 用户 "bob"@"acme.com" 尝试访问该状态
    那么 访问决策应当为 false

  场景: 边界 - 匹配 owner 的请求允许访问
    假设 已存在 debug 状态 owner={"username":"alice","domain":"acme.com"} status="running"
    当 用户 "alice"@"acme.com" 尝试访问该状态
    那么 访问决策应当为 true

  场景: 边界 - 跨 domain 同 username 仍被视为不同 owner
    假设 已存在 debug 状态 owner={"username":"alice","domain":"acme.com"} status="running"
    当 用户 "alice"@"other.com" 尝试访问该状态
    那么 访问决策应当为 false

  场景: 边界 - 调度配置 cycle_value_type 变化会触发重调度
    假设 旧任务 is_interval=true cycle_value="5" cycle_value_type="cycle" scan_cycle="*/5 * * * *"
    并且 新任务 is_interval=true cycle_value="5" cycle_value_type="timing" scan_cycle="*/5 * * * *"
    当 我调用 is_schedule_config_changed
    那么 调度变化结果应当为 true

  场景: 边界 - 调度 is_interval 从 true 变 false 触发重调度
    假设 旧任务 is_interval=true cycle_value="5" cycle_value_type="cycle" scan_cycle="*/5 * * * *"
    并且 新任务 is_interval=false cycle_value="5" cycle_value_type="cycle" scan_cycle=""
    当 我调用 is_schedule_config_changed
    那么 调度变化结果应当为 true
