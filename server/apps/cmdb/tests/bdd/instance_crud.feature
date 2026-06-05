# language: zh-CN
功能: CMDB 实例增删改主链路
  作为 CMDB 实例使用者
  为了管理资产实例的完整生命周期
  InstanceManage 必须正确编排校验 / 落图库 / 写变更记录 / 触发自动关联

  背景:
    假设 实例服务的旁路依赖已被打桩

  # ---------- Happy Path ----------

  场景: 正常路径 - 创建主机实例落库并触发自动关联
    假设 模型 "host" 存在，属性中 "inst_name" 必填
    当 用户 "admin" 创建实例 model_id="host" payload={"inst_name":"web-01"} allowed_org_ids=[1]
    那么 实例创建应当成功
    并且 返回实例的 inst_name 应当为 "web-01"
    并且 应当对图库执行过 1 次 create_entity
    并且 自动关联补齐应当被触发 1 次

  场景: 正常路径 - 更新实例的 inst_name
    假设 实例 _id=5 model_id="host" inst_name="h1" organization=[1] 存在
    当 用户 "admin" 更新实例 _id=5 payload={"inst_name":"h2"}
    那么 实例更新应当成功
    并且 更新返回的 inst_name 应当为 "h2"

  场景: 正常路径 - 批量删除多个实例
    假设 实例集合为 [{"_id":1,"model_id":"host","inst_name":"h1","organization":[1]},{"_id":2,"model_id":"host","inst_name":"h2","organization":[1]}]
    当 用户 "admin" 批量删除实例 ids=[1,2]
    那么 应当对图库执行过 batch_delete_entity
    并且 自动关联反向同步应当被触发 1 次

  # ---------- Corner Case ----------

  场景: 边界 - 更新不存在的实例抛业务异常
    假设 实例 _id=99 不存在
    当 用户 "admin" 尝试更新实例 _id=99 payload={"inst_name":"x"}
    那么 应当抛出业务异常，消息包含 "实例不存在"

  场景: 边界 - 批量删除空列表立即拒绝
    假设 query_entity_by_ids 返回空列表
    当 用户 "admin" 尝试批量删除实例 ids=[]
    那么 应当抛出业务异常，消息包含 "实例不存在"

  场景: 边界 - 实例创建时 allowed_org_ids 不含目标 org 越权被拒
    假设 模型 "host" 存在，属性中 "inst_name" 必填
    当 用户 "admin" 尝试创建实例 model_id="host" payload={"inst_name":"x","organization":[99]} allowed_org_ids=[1]
    那么 应当抛出业务异常，消息包含 "组织"

  场景: 边界 - 批量更新空实例列表抛异常
    假设 query_entity_by_ids 返回空列表
    当 用户 "admin" 尝试批量更新实例 ids=[1] payload={"inst_name":"x"}
    那么 应当抛出业务异常，消息包含 "实例不存在"

  场景: 边界 - 批量更新成功路径
    假设 实例集合为 [{"_id":1,"model_id":"host","inst_name":"h1","organization":[1]}]
    当 用户 "admin" 批量更新实例 ids=[1] payload={"inst_name":"h2"}
    那么 批量更新返回首条实例的 inst_name 应当为 "h2"

  场景: 边界 - 关联创建时调用了 create_edge
    假设 关联校验放行
    当 用户 "admin" 创建关联 src=1 dst=2 model_asst_id="host_conn_switch"
    那么 应当对图库执行过 create_edge
