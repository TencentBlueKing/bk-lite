# language: zh-CN
功能: 告警自动分派策略
  作为告警平台
  为了让未分派告警按既定规则自动落到值班人手里
  AlertAssignmentOperator 必须在生效策略与匹配规则下正确驱动状态机

  背景:
    假设 存在团队为 1 的系统用户 "op1"

  # ---------- Happy Path ----------

  场景: 正常路径 - match_type=all 的策略对所有未分派告警自动分派
    假设 已存在未分派告警 "A1" title="CPU高"
    并且 已存在分派策略 name="全部" match_type="all" personnel=["op1"]
    当 我对告警 ["A1"] 执行自动分派
    那么 告警 "A1" 的状态应当为 "pending"

  场景: 正常路径 - match_type=filter 的策略只匹配命中规则的告警
    假设 已存在未分派告警 "A1" title="CPU高"
    并且 已存在未分派告警 "A2" title="内存正常"
    并且 已存在分派策略 name="CPU策略" match_type="filter" personnel=["op1"] match_rules=[[{"key":"title","operator":"contains","value":"CPU"}]]
    当 我对告警 ["A1","A2"] 执行自动分派
    那么 告警 "A1" 的状态应当为 "pending"
    并且 告警 "A2" 的状态应当为 "unassigned"

  # ---------- Corner Case ----------

  场景: 边界 - 没有任何活跃分派策略时所有告警保持未分派
    假设 已存在未分派告警 "A1" title="CPU高"
    当 我对告警 ["A1"] 执行自动分派
    那么 已分派告警数应当为 0
    并且 告警 "A1" 的状态应当为 "unassigned"

  场景: 边界 - 分派策略 personnel 为空时分派失败
    假设 已存在未分派告警 "A1" title="CPU高"
    并且 已存在分派策略 name="无人员" match_type="all" personnel=[]
    当 我对告警 ["A1"] 执行自动分派
    那么 已分派告警数应当为 0
    并且 告警 "A1" 的状态应当为 "unassigned"

  场景: 边界 - 自动分派接收空告警列表立即返回 0
    当 我对告警 [] 执行自动分派
    那么 总告警数应当为 0

  场景: 边界 - 自动分派引用不存在的告警 ID 应抛 AlertNotFoundError
    当 我尝试对告警 ["GHOST"] 构造分派操作员
    那么 应当抛出告警不存在异常

  场景: 边界 - filter 规则未命中时告警保持未分派
    假设 已存在未分派告警 "A1" title="磁盘满"
    并且 已存在分派策略 name="CPU策略" match_type="filter" personnel=["op1"] match_rules=[[{"key":"title","operator":"contains","value":"CPU"}]]
    当 我对告警 ["A1"] 执行自动分派
    那么 告警 "A1" 的状态应当为 "unassigned"
