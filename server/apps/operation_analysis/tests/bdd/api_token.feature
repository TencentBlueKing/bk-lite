# language: zh-CN
功能: 运营分析 API Token 权限校验
  作为第三方接入方
  为了用 API Token 调用运营分析的数据源 / 画布接口
  HasPermission 装饰器必须基于 user.permission 与 superuser 决定放行或返回 403

  # ---------- Happy Path ----------

  场景: 正常路径 - 携带 view-View 权限的 token 可访问列表
    假设 当前 user 拥有权限映射 {"ops-analysis":["view-View"]} is_superuser=false
    当 API Token 调用受 "view-View" 保护的接口
    那么 响应状态码应当为 200

  场景: 正常路径 - 超级用户无需显式权限即可访问
    假设 当前 user 是 superuser
    当 API Token 调用受 "view-View" 保护的接口
    那么 响应状态码应当为 200

  # ---------- Corner Case ----------

  场景: 边界 - 无任何权限的 token 被拒
    假设 当前 user 拥有权限映射 {} is_superuser=false
    当 API Token 调用受 "view-View" 保护的接口
    那么 响应状态码应当为 403

  场景: 边界 - 持有错误 app 的权限 token 被拒
    假设 当前 user 拥有权限映射 {"other-app":["view-View"]} is_superuser=false
    当 API Token 调用受 "view-View" 保护的接口
    那么 响应状态码应当为 403

  场景: 边界 - 持有同 app 但不同权限名 token 被拒
    假设 当前 user 拥有权限映射 {"ops-analysis":["edit-Edit"]} is_superuser=false
    当 API Token 调用受 "view-View" 保护的接口
    那么 响应状态码应当为 403

  场景: 边界 - is_superuser 字段优先于 permission 映射
    假设 当前 user 拥有权限映射 {} is_superuser=true
    当 API Token 调用受 "view-View" 保护的接口
    那么 响应状态码应当为 200
