# language: zh-CN
功能: 运营分析数据源（NameSpace + DataSourceAPIModel）
  作为运营分析平台
  为了让画布按租户隔离接入 NATS 数据源，并保证凭据安全
  数据源模型必须维护唯一约束、密码加解密、按团队过滤、可见性 editable 标记

  # ---------- Happy Path ----------

  场景: 正常路径 - 新建 NameSpace 并对密码自动加密
    当 我创建 NameSpace name="ns1" account="acc" password="plain123" domain="127.0.0.1:4222"
    那么 NameSpace 创建应当成功
    并且 数据库中存在 NameSpace name="ns1"
    并且 decrypt_password 应当能还原为 "plain123"

  场景: 正常路径 - 新建 DataSourceAPIModel 关联 NameSpace
    假设 已存在 NameSpace "ns1"
    当 我创建 DataSourceAPIModel name="活跃告警" rest_api="monitor/active" groups=[1] 并关联 NameSpace "ns1"
    那么 数据源创建应当成功
    并且 数据源关联的 NameSpace 数量应当为 1

  场景: 正常路径 - 数据源被基础过滤后按团队隔离
    假设 已存在数据源 "ds_t1" groups=[1]
    并且 已存在数据源 "ds_t2" groups=[2]
    当 我以 current_team=1 调用 apply_group_filter
    那么 结果数据源应当恰好包含 "ds_t1"

  # ---------- Corner Case ----------

  场景: 边界 - NameSpace 名称唯一约束防重复
    假设 已存在 NameSpace "ns1"
    当 我尝试创建 NameSpace name="ns1" account="acc2" password="x" domain="d2"
    那么 应当抛出唯一约束异常

  场景: 边界 - 数据源 (name, rest_api) 联合唯一防重复
    假设 已存在数据源 name="A" rest_api="/x" groups=[1]
    当 我尝试创建数据源 name="A" rest_api="/x" groups=[1]
    那么 应当抛出唯一约束异常

  场景: 边界 - 设置空密码不触发加密直接落库
    当 我创建 NameSpace name="ns_empty" account="a" password="" domain="d"
    那么 NameSpace 创建应当成功
    并且 数据库中 "ns_empty" 的 password 字段为空

  场景: 边界 - 已加密密码再次 set_password 仍能解密回明文
    假设 已存在 NameSpace "ns2" password="orig"
    当 我对 "ns2" 调用 set_password("rotated") 并保存
    那么 decrypt_password 应当能还原为 "rotated"

  场景: 边界 - DataSourceTag 名称唯一约束防重复
    假设 已存在 DataSourceTag tag_id="t1" name="标签A"
    当 我尝试创建 DataSourceTag tag_id="t2" name="标签A"
    那么 应当抛出唯一约束异常
