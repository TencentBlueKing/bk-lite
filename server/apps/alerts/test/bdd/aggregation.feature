# language: zh-CN
功能: 告警聚合处理器
  作为告警平台
  为了在事件抵达时按相关性规则与心跳模式做聚合 / 心跳检测
  AggregationProcessor 必须正确加载策略参数、构造心跳上下文、按时间窗取事件

  背景:
    假设 存在告警源 "源1" source_id="s1"

  # ---------- Happy Path ----------

  场景: 正常路径 - 策略未设置参数时回填默认值
    假设 一个策略 params={}
    当 我加载策略参数
    那么 策略 check_mode 应当为 "cron"
    并且 策略 grace_period 应当为 0
    并且 策略 auto_recovery 应当为 true

  场景: 正常路径 - 已显式提供的策略参数应被保留
    假设 一个策略 params={"grace_period":5,"cron_expr":"* * * * *"}
    当 我加载策略参数
    那么 策略 grace_period 应当为 5
    并且 策略 cron_expr 应当为 "* * * * *"

  # ---------- Corner Case ----------

  场景: 边界 - 时间窗内的事件会被策略取到
    假设 已存在事件 "E1" title="t"
    并且 已存在 smart_denoise 策略 name="s" params={"window_size":60}
    当 我对策略调用 get_events_for_strategy
    那么 候选事件应当包含 "E1"

  场景: 边界 - 解析空字符串的运行时时间返回 None
    当 我解析运行时时间 ""
    那么 解析结果应当为 None

  场景: 边界 - 解析 ISO 格式时间应自动带时区
    当 我解析运行时时间 "2026-01-01T10:00:00"
    那么 解析结果应当带时区

  场景: 边界 - normalize_to_project_timezone 对 None 返回 None
    当 我规范化时间 None
    那么 规范化结果应当为 None

  场景: 边界 - heartbeat_context 字段从事件取出
    假设 事件具备 service="svc" item="cpu" level="0"
    当 我构造 heartbeat 上下文
    那么 上下文 service 应当为 "svc"
    并且 上下文 item 应当为 "cpu"
    并且 上下文 level 应当为 "0"
