# language: zh-CN
功能: 运营分析画布（Dashboard / Topology / Architecture）
  作为运营分析平台
  为了让用户在多团队场景下创建、隔离和复用各类画布
  画布模型必须维护名称唯一、内置标识唯一、目录归属、按团队 editable 标记

  # ---------- Happy Path ----------

  场景: 正常路径 - 创建一个 Dashboard 落库
    假设 已存在目录 "默认目录" groups=[1]
    当 我创建 Dashboard name="资产健康度" desc="" 归属目录 "默认目录" groups=[1]
    那么 画布创建应当成功
    并且 数据库中存在 Dashboard name="资产健康度"

  场景: 正常路径 - Dashboard 按团队 apply_group_filter 隔离
    假设 已存在 Dashboard "d1" groups=[1]
    并且 已存在 Dashboard "d2" groups=[2]
    当 我以 current_team=1 调用 apply_group_filter
    那么 结果画布应当恰好包含 "d1"

  # ---------- Corner Case ----------

  场景: 边界 - Dashboard 名称唯一约束防重复
    假设 已存在 Dashboard "dup" groups=[1]
    当 我尝试创建 Dashboard name="dup" desc="" groups=[1]
    那么 应当抛出唯一约束异常

  场景: 边界 - 内置 Dashboard build_in_key 唯一约束防重复
    假设 已存在内置 Dashboard "buildin1" build_in_key="bk_alerts" groups=[1]
    当 我尝试创建内置 Dashboard "buildin2" build_in_key="bk_alerts" groups=[1]
    那么 应当抛出唯一约束异常

  场景: 边界 - 删除目录级联删除目录下的所有 Dashboard
    假设 已存在目录 "待删目录" groups=[1]
    并且 已存在 Dashboard "d_under" groups=[1] 归属目录 "待删目录"
    当 我删除目录 "待删目录"
    那么 数据库中不应再存在 Dashboard "d_under"

  场景: 边界 - Dashboard 未指定目录可独立保存
    当 我创建 Dashboard name="无目录画布" desc="" 不归属任何目录 groups=[1]
    那么 画布创建应当成功
    并且 Dashboard "无目录画布" 的 directory 应当为 None
