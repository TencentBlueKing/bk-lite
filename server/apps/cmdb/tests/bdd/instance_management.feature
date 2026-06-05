# language: zh-CN
功能: CMDB 实例管理
  作为 CMDB 实例管理员
  为了让实例 CRUD 与拓扑展示遵循模型字段约束与组织权限
  InstanceManage 必须正确生成校验属性映射、汇总导入结果、按权限裁剪拓扑

  # ---------- Happy Path ----------

  场景: 正常路径 - 根据模型属性构造创建场景的校验属性映射
    假设 模型属性集合为 [{"attr_id":"ip","attr_name":"IP","is_only":true,"is_required":true},{"attr_id":"name","attr_name":"主机名","is_only":false,"is_required":true},{"attr_id":"desc","attr_name":"描述","is_only":false,"is_required":false}]
    当 我以非更新场景构造 check_attr_map
    那么 is_only 映射的键集合应当为 ["ip"]
    并且 is_required 映射的键集合应当为 ["ip","name"]
    并且 check_attr_map 中不应包含 "editable" 键

  场景: 正常路径 - 更新场景下的 check_attr_map 包含 editable 集合
    假设 模型属性集合为 [{"attr_id":"ip","attr_name":"IP","is_only":true,"is_required":true,"editable":false},{"attr_id":"name","attr_name":"主机名","is_only":false,"is_required":true,"editable":true}]
    当 我以更新场景构造 check_attr_map
    那么 editable 映射的键集合应当为 ["name"]

  场景: 正常路径 - 导入结果完全成功时返回空摘要并标记成功
    假设 一个全成功的导入结果 add=2 update=3 asso=1
    当 我调用 format_result_message
    那么 整体状态应当为 true
    并且 摘要消息应当为空

  # ---------- Corner Case ----------

  场景: 边界 - 导入结果出现失败时摘要非空且整体状态为 false
    假设 一个导入结果 add=1 add_error=1 add_data=["dup"] update=0 update_error=0 asso=0 asso_error=0
    当 我调用 format_result_message
    那么 整体状态应当为 false
    并且 摘要消息应当包含 "新增: 成功1个，失败1个"
    并且 摘要消息应当包含 "dup"

  场景: 边界 - 拓扑节点权限裁剪：保留可见子树并裁掉不可见节点
    假设 一棵以 _id=1 为根、子节点为 [2,3] 的拓扑
    并且 可见节点集合为 [1,2]
    当 我以中心节点 1 裁剪拓扑
    那么 裁剪后的子节点 ids 应当为 [2]

  场景: 边界 - 根节点既非中心也不可见时整棵被裁剪
    假设 一棵以 _id=5 为根、无子节点的拓扑
    并且 可见节点集合为空
    当 我以中心节点 1 裁剪拓扑
    那么 裁剪结果应当为空对象

  场景: 边界 - 实例为 None 时拓扑权限校验直接拒绝
    当 我对 None 实例调用 _has_topology_view_permission
    那么 校验结果应当为 false

  场景: 边界 - 创建者命中且组织在权限映射中时拓扑权限放行
    假设 实例 _creator="alice" organization=[4] model_id="host"
    并且 权限映射 {4: {"permission_instances_map": {}}}
    并且 当前用户 username="alice"
    当 我调用 _has_topology_view_permission
    那么 校验结果应当为 true
