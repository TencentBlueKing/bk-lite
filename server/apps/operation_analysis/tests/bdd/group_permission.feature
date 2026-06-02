# language: zh-CN
功能: 运营分析团队权限隔离
  作为运营分析模块的租户
  为了保持仪表盘和数据源按团队隔离
  GroupPermissionMixin 必须强制执行 current_team 规则与 queryset 过滤

  # ---------- Happy Path ----------

  场景: 正常路径 - 有效 current_team cookie 通过组校验
    假设 一个 GET 请求 current_team 为 "2"
    当 我执行 validate_group_permission
    那么 校验应当通过，团队为 2

  场景: 正常路径 - 按团队 id 过滤目录 queryset
    假设 存在目录 "in-team" 隶属组 [1]
    并且 存在目录 "other-team" 隶属组 [2]
    当 我使用 current_team 1 执行 apply_group_filter
    那么 结果目录应当恰好为 ["in-team"]

  # ---------- Corner Case ----------

  场景: 边界 - 缺少 current_team cookie 校验失败
    假设 一个 GET 请求未携带 current_team
    当 我执行 validate_group_permission
    那么 校验应当失败

  场景: 边界 - 非数字 current_team 校验失败
    假设 一个 GET 请求 current_team 为 "notanumber"
    当 我执行 validate_group_permission
    那么 校验应当失败

  场景: 边界 - 未携带 all_groups 参数时全组权限拒绝
    假设 一个 GET 请求未携带 all_groups 参数
    当 我执行 validate_all_groups_permission
    那么 全组校验应当被拒绝

  场景: 边界 - 携带 all_groups=1 时全组权限放行
    假设 一个 GET 请求 all_groups 参数为 "1"
    当 我执行 validate_all_groups_permission
    那么 全组校验应当通过

  场景: 边界 - 超级用户 current_team 为空，不做过滤
    假设 存在目录 "su-1" 隶属组 [1]
    并且 存在目录 "su-2" 隶属组 [2]
    当 我使用 current_team None 执行 apply_group_filter
    那么 结果目录数量应当等于源数量

  场景: 边界 - 指定 user 时叠加 created_by 过滤
    假设 存在目录 "mine" 隶属组 [1]，创建人为 "testuser"
    并且 存在目录 "theirs" 隶属组 [1]，创建人为 "someoneelse"
    当 我使用 current_team 1 与用户 "testuser" 执行 apply_group_filter
    那么 结果目录应当恰好为 ["mine"]
