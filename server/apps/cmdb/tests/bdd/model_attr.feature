# language: zh-CN
功能: CMDB 模型属性管理
  作为 CMDB 模型管理员
  为了维护模型字段约束
  ModelManage 必须在新增/修改属性时执行 attr_id 校验、不可变约束、tag/enum 专属规则

  背景:
    假设 模型属性服务的旁路依赖已被打桩

  # ---------- Happy Path ----------

  场景: 正常路径 - 在模型上新增一个普通属性
    假设 图库中存在模型 model_id="host" model_name="主机" attrs="[]"
    当 用户 "admin" 创建模型属性 model_id="host" attr={"attr_id":"mem","attr_name":"内存","attr_type":"int","is_required":false,"editable":true}
    那么 属性创建应当成功
    并且 新增属性的 attr_id 应当为 "mem"

  场景: 正常路径 - 修改属性的展示名称
    假设 图库中存在模型 model_id="host" model_name="主机" attrs=[{"attr_id":"ip","attr_name":"IP","attr_type":"str","editable":true,"is_required":true,"is_only":false,"attr_group":"g","option":{},"user_prompt":""}]
    当 用户 "admin" 更新模型属性 model_id="host" attr={"attr_id":"ip","attr_name":"IPv4","attr_type":"str","editable":true,"is_required":true,"is_only":false,"attr_group":"g","option":{},"user_prompt":"","default_value":[]}
    那么 属性更新应当成功
    并且 更新后的属性 attr_name 应当为 "IPv4"

  场景: 正常路径 - 删除一个非预置属性
    假设 图库中存在模型 model_id="host" model_name="主机" attrs=[{"attr_id":"mem","attr_name":"内存","attr_type":"int"}]
    当 用户 "admin" 删除模型属性 model_id="host" attr_id="mem"
    那么 属性删除应当成功

  # ---------- Corner Case ----------

  场景: 边界 - 创建重复 attr_id 被拒
    假设 图库中存在模型 model_id="host" model_name="主机" attrs=[{"attr_id":"ip","attr_name":"IP","attr_type":"str"}]
    当 用户 "admin" 尝试创建模型属性 model_id="host" attr={"attr_id":"ip","attr_name":"IP2","attr_type":"str"}
    那么 应当抛出业务异常，消息包含 "repetition"

  场景: 边界 - 在不存在的模型上创建属性被拒
    假设 图库中没有任何模型
    当 用户 "admin" 尝试创建模型属性 model_id="missing" attr={"attr_id":"x","attr_name":"x","attr_type":"str"}
    那么 应当抛出业务异常，消息包含 "model not present"

  场景: 边界 - 更新不存在的属性被拒
    假设 图库中存在模型 model_id="host" model_name="主机" attrs=[]
    当 用户 "admin" 尝试更新模型属性 model_id="host" attr={"attr_id":"ghost","attr_name":"鬼","attr_type":"str","editable":true,"is_required":false,"is_only":false,"attr_group":"g","option":{},"user_prompt":"","default_value":[]}
    那么 应当抛出业务异常，消息包含 "model attr not present"

  场景: 边界 - 枚举字段 enum_rule_type 不可从 custom 切到 public_library
    假设 当前属性 attr_type="enum" enum_rule_type="custom"
    并且 传入属性 attr_type="enum" enum_rule_type="public_library"
    当 我调用 validate_enum_rule_immutable
    那么 应当抛出业务异常，消息包含 "规则类型不可切换"

  场景: 边界 - 枚举字段 enum_select_mode 不可从 single 切到 multiple
    假设 当前属性 attr_type="enum" enum_select_mode="single"
    并且 传入属性 attr_type="enum" enum_select_mode="multiple"
    当 我调用 validate_enum_select_mode_immutable
    那么 应当抛出业务异常，消息包含 "选择模式不可切换"

  场景: 边界 - enum 属性创建时未提供 enum_select_mode 应自动回填为 single
    假设 待规范属性 attr_type="enum"
    当 我调用 ensure_enum_select_mode
    那么 属性 enum_select_mode 应当为 "single"
