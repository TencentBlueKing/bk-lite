# language: zh-CN
功能: CMDB 自动关联规则
  作为 CMDB 管理员
  为了让相同字段值的实例之间自动建立关联
  自动关联规则定义必须经过字段存在/类型/匹配规则合法性校验

  # ---------- Happy Path ----------

  场景: 正常路径 - 同类型字符串字段的精确匹配规则通过校验
    假设 源模型属性 [{"attr_id":"host_ip","attr_type":"str"}]
    并且 目标模型属性 [{"attr_id":"ip","attr_type":"str"}]
    当 我校验自动关联规则 payload={"match_pairs":[{"src_field_id":"host_ip","dst_field_id":"ip","matching_rule":"exact"}]}
    那么 校验应当通过
    并且 返回的规则启用状态应当为 true

  场景: 正常路径 - 字段类型为 int 的精确匹配通过
    假设 源模型属性 [{"attr_id":"port","attr_type":"int"}]
    并且 目标模型属性 [{"attr_id":"listen_port","attr_type":"int"}]
    当 我校验自动关联规则 payload={"match_pairs":[{"src_field_id":"port","dst_field_id":"listen_port","matching_rule":"exact"}]}
    那么 校验应当通过

  # ---------- Corner Case ----------

  场景: 边界 - match_pairs 为空时被拒
    假设 源模型属性 [{"attr_id":"x","attr_type":"str"}]
    并且 目标模型属性 [{"attr_id":"y","attr_type":"str"}]
    当 我校验自动关联规则 payload={"match_pairs":[]}
    那么 应当抛出业务异常，消息包含 "match_pairs 不能为空"

  场景: 边界 - 源字段不存在时被拒
    假设 源模型属性 [{"attr_id":"a","attr_type":"str"}]
    并且 目标模型属性 [{"attr_id":"b","attr_type":"str"}]
    当 我校验自动关联规则 payload={"match_pairs":[{"src_field_id":"missing","dst_field_id":"b","matching_rule":"exact"}]}
    那么 应当抛出业务异常，消息包含 "源字段"

  场景: 边界 - 目标字段不存在时被拒
    假设 源模型属性 [{"attr_id":"a","attr_type":"str"}]
    并且 目标模型属性 [{"attr_id":"b","attr_type":"str"}]
    当 我校验自动关联规则 payload={"match_pairs":[{"src_field_id":"a","dst_field_id":"missing","matching_rule":"exact"}]}
    那么 应当抛出业务异常，消息包含 "目标字段"

  场景: 边界 - 源目标字段类型不一致时被拒
    假设 源模型属性 [{"attr_id":"a","attr_type":"str"}]
    并且 目标模型属性 [{"attr_id":"b","attr_type":"int"}]
    当 我校验自动关联规则 payload={"match_pairs":[{"src_field_id":"a","dst_field_id":"b","matching_rule":"exact"}]}
    那么 应当抛出业务异常，消息包含 "类型不一致"

  场景: 边界 - payload 不是 dict 时被拒
    假设 源模型属性 []
    并且 目标模型属性 []
    当 我校验自动关联规则 payload=null
    那么 应当抛出业务异常，消息包含 "配置不合法"
