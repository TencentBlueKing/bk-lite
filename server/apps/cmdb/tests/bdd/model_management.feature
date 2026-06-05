# language: zh-CN
功能: CMDB 模型管理（分类 + 模型）
  作为 CMDB 管理员
  为了维护资产模型的分类树和模型本身
  ClassificationManage / ModelManage 必须正确写入图库、维护引用完整性、过滤不可变字段

  背景:
    假设 图库可以被 FakeGraphClient 替换

  # ---------- Happy Path ----------

  场景: 正常路径 - 新建模型分类成功落库
    当 管理员创建模型分类 classification_id="biz" classification_name="业务"
    那么 应当对图库 "classification" 执行 1 次 create_entity
    并且 返回的分类应包含 classification_id="biz"

  场景: 正常路径 - 更新模型分类时排除自身后再做唯一性比对
    假设 图库中已存在分类记录 _id=10 classification_id="net" classification_name="网络"
    并且 图库中已存在分类记录 _id=11 classification_id="biz" classification_name="业务"
    当 管理员更新分类 _id=10 字段 classification_name="网络v2"
    那么 set_entity_properties 调用时 exist_items 不应包含 _id=10

  场景: 正常路径 - 分类列表会按是否存在模型标记 exist_model
    假设 图库中已存在分类记录 _id=10 classification_id="biz" classification_name="业务"
    并且 图库中已存在分类记录 _id=11 classification_id="net" classification_name="网络"
    并且 图库中已存在模型记录 model_id="host" classification_id="biz"
    当 用户查询模型分类列表
    那么 分类 "biz" 的 exist_model 应当为 true
    并且 分类 "net" 的 exist_model 应当为 false

  # ---------- Corner Case ----------

  场景: 边界 - 删除分类前若分类被模型使用应抛出异常
    假设 图库中已存在模型记录 model_id="host" classification_id="biz"
    当 管理员尝试校验分类 "biz" 是否被使用
    那么 应当抛出业务异常，消息包含 "classification is used"

  场景: 边界 - 校验未被使用的分类不抛异常
    当 管理员尝试校验分类 "empty" 是否被使用
    那么 校验应当通过

  场景: 边界 - 删除存在实例的模型抛出异常
    假设 图库中存在 model_id="host" 的实例 1 条
    当 管理员尝试校验模型 "host" 是否存在实例
    那么 应当抛出业务异常，消息包含 "model exist instance"

  场景: 边界 - 模型存在关联关系时禁止删除
    假设 模型 "host" 存在关联边 1 条
    当 管理员尝试校验模型 "host" 是否存在关联
    那么 应当抛出业务异常，消息包含 "model association exist"

  场景: 边界 - 更新模型时 model_id 字段会被剥离不允许变更
    假设 图库中已存在模型记录 model_id="host" classification_id="biz"
    当 管理员更新模型 _id=20 字段 model_id="evil" model_name="主机v2"
    那么 set_entity_properties 调用时 payload 中不应包含 "model_id"
    并且 set_entity_properties 调用时 payload 中应包含 "model_name"
