# language: zh-CN
功能: CMDB 唯一性规则
  作为模型管理员
  为了让"联合字段唯一"约束在实例落库前被准确检测
  unique_rule 服务必须正确生成冲突、保护既有实例、并校验规则定义合法性

  # ---------- Happy Path ----------

  场景: 正常路径 - 唯一规则不冲突时新实例可被接收
    假设 模型唯一规则定义为 [{"rule_id":"r1","order":1,"field_ids":["ip","port"]}]
    并且 模型属性映射为 {"ip":{"attr_name":"IP"},"port":{"attr_name":"端口"}}
    并且 既有实例集合为 [{"_id":1,"ip":"10.0.0.1","port":22}]
    当 我检查批次 [{"ip":"10.0.0.2","port":22}] 是否冲突
    那么 冲突数量应当为 0

  场景: 正常路径 - 编辑现有实例时排除自身后通过校验
    假设 模型唯一规则定义为 [{"rule_id":"r1","order":1,"field_ids":["ip"]}]
    并且 模型属性映射为 {"ip":{"attr_name":"IP"}}
    并且 既有实例集合为 [{"_id":7,"ip":"10.0.0.1"}]
    当 我以排除 ids=[7] 检查批次 [{"ip":"10.0.0.1"}] 是否冲突
    那么 冲突数量应当为 0

  # ---------- Corner Case ----------

  场景: 边界 - 联合字段命中既有实例时产生冲突
    假设 模型唯一规则定义为 [{"rule_id":"r1","order":1,"field_ids":["ip","port"]}]
    并且 模型属性映射为 {"ip":{"attr_name":"IP"},"port":{"attr_name":"端口"}}
    并且 既有实例集合为 [{"_id":1,"ip":"10.0.0.1","port":22,"inst_name":"h1"}]
    当 我检查批次 [{"ip":"10.0.0.1","port":22}] 是否冲突
    那么 冲突数量应当为 1

  场景: 边界 - 同一批次内重复行产生批次内冲突
    假设 模型唯一规则定义为 [{"rule_id":"r1","order":1,"field_ids":["ip"]}]
    并且 模型属性映射为 {"ip":{"attr_name":"IP"}}
    并且 既有实例集合为 []
    当 我检查批次 [{"ip":"10.0.0.5"},{"ip":"10.0.0.5"}] 是否冲突
    那么 冲突数量应当为 1
    并且 冲突消息应当包含 "本批次"

  场景: 边界 - 唯一规则字段为空时 payload 校验拒绝
    假设 唯一规则上下文 attrs={"ip":{"attr_name":"IP","is_required":true,"attr_type":"str"}} 现有规则数=0
    当 我以 payload field_ids=[] 校验规则
    那么 应当抛出业务异常，消息包含 "不能为空"

  场景: 边界 - 唯一规则字段含 inst_name 时拒绝
    假设 唯一规则上下文 attrs={"inst_name":{"attr_name":"名称","is_required":true,"attr_type":"str"}} 现有规则数=0
    当 我以 payload field_ids=["inst_name"] 校验规则
    那么 应当抛出业务异常，消息包含 "不允许包含 inst_name"

  场景: 边界 - 唯一规则字段非必填时拒绝
    假设 唯一规则上下文 attrs={"foo":{"attr_name":"foo","is_required":false,"attr_type":"str"}} 现有规则数=0
    当 我以 payload field_ids=["foo"] 校验规则
    那么 应当抛出业务异常，消息包含 "不是必填"

  场景: 边界 - 唯一规则数量已达上限不允许新增
    假设 唯一规则上下文 attrs={"a":{"attr_name":"a","is_required":true,"attr_type":"str"}} 现有规则数=3
    当 我以 payload field_ids=["a"] 校验规则
    那么 应当抛出业务异常，消息包含 "最多只能配置"
