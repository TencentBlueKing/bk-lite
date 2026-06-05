# language: zh-CN
功能: CMDB 公共选项库（PublicEnumLibrary）业务规则
  作为 CMDB 模型管理员
  为了让多个模型属性共享同一份枚举字典
  公共选项库服务必须严格校验输入、维护引用完整性、在 options 变更时同步快照

  背景:
    假设 公共选项库表已就绪
    并且 模型库中没有任何模型属性引用现有选项库

  # ---------- Happy Path ----------

  场景: 正常路径 - 管理员可以新建一个含两条选项的选项库
    当 管理员 "admin" 创建选项库 name="资产状态" team=[1] options=[{"id":"1","name":"运行"},{"id":"2","name":"停用"}]
    那么 创建应当成功
    并且 返回结果的 name 应当为 "资产状态"
    并且 返回结果的 options 数量应当为 2
    并且 数据库中应当存在 library_id 对应的记录

  场景: 正常路径 - 更新选项库的 options 会触发快照同步任务
    假设 已存在选项库 "lib_alpha" name="状态" team=[1] options=[{"id":"1","name":"运行"}]
    当 管理员 "admin" 更新选项库 "lib_alpha" 字段 options=[{"id":"1","name":"运行"},{"id":"2","name":"维护"}]
    那么 更新应当成功
    并且 快照同步任务应当被触发 1 次

  场景: 正常路径 - 仅更新名称不会触发快照同步
    假设 已存在选项库 "lib_beta" name="旧名" team=[1] options=[{"id":"1","name":"a"}]
    当 管理员 "admin" 更新选项库 "lib_beta" 字段 name="新名"
    那么 更新应当成功
    并且 数据库中 "lib_beta" 的名称应当为 "新名"
    并且 快照同步任务应当被触发 0 次

  场景: 正常路径 - 未被任何模型属性引用的选项库可被删除
    假设 已存在选项库 "lib_gamma" name="待删" team=[1] options=[{"id":"1","name":"a"}]
    当 管理员 "admin" 删除选项库 "lib_gamma"
    那么 删除应当成功
    并且 数据库中不应再存在 "lib_gamma"

  场景: 正常路径 - 按团队列出可见的选项库并标记可编辑性
    假设 已存在选项库 "lib_t1" name="t1库" team=[1] options=[{"id":"1","name":"a"}]
    并且 已存在选项库 "lib_t2" name="t2库" team=[2] options=[{"id":"1","name":"a"}]
    当 当前用户以团队 [1] 调用 list_libraries
    那么 返回的选项库数量应当为 2
    并且 选项库 "lib_t1" 的 editable 应当为 true
    并且 选项库 "lib_t2" 的 editable 应当为 false

  # ---------- Corner Case ----------

  场景: 边界 - 创建时名称为空被拒绝
    当 管理员 "admin" 尝试创建选项库 name="   " team=[1] options=[{"id":"1","name":"a"}]
    那么 应当抛出业务异常，消息包含 "名称不能为空"

  场景: 边界 - 创建时 team 非数组被拒绝
    当 管理员 "admin" 尝试创建选项库 name="库" team="1" options=[{"id":"1","name":"a"}]
    那么 应当抛出业务异常，消息包含 "team 必须是数组"

  场景: 边界 - 创建时 options 中存在重复 id 被拒绝
    当 管理员 "admin" 尝试创建选项库 name="库" team=[1] options=[{"id":"1","name":"a"},{"id":"1","name":"b"}]
    那么 应当抛出业务异常，消息包含 "重复的 id"

  场景: 边界 - 创建时 option 缺失 id 被拒绝
    当 管理员 "admin" 尝试创建选项库 name="库" team=[1] options=[{"name":"无id"}]
    那么 应当抛出业务异常，消息包含 "id 必须是非空字符串"

  场景: 边界 - 创建时 options 含非对象元素被拒绝
    当 管理员 "admin" 尝试创建选项库 name="库" team=[1] options=["bad"]
    那么 应当抛出业务异常，消息包含 "必须是对象"

  场景: 边界 - 更新不存在的选项库被拒绝
    当 管理员 "admin" 尝试更新选项库 "lib_not_exist" 字段 name="x"
    那么 应当抛出业务异常，消息包含 "公共选项库不存在"

  场景: 边界 - 被模型属性引用的选项库不可删除并返回引用清单
    假设 已存在选项库 "lib_in_use" name="使用中" team=[1] options=[{"id":"1","name":"a"}]
    并且 模型 "host"（主机）的属性 "status"（状态）引用了 "lib_in_use"
    当 管理员 "admin" 尝试删除选项库 "lib_in_use"
    那么 应当抛出业务异常，消息包含 "正在被以下属性引用"
    并且 异常数据中的 references 长度应当为 1
    并且 数据库中仍然存在 "lib_in_use"
