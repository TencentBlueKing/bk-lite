# Spec — Issue #4086 日志分组规则模式收敛

## 根因

日志分组 `rule` 是无结构 `JSONField`。写入边界不校验 `mode`，读取边界只特判 `AND`，其余字符串都按 `OR` 执行，导致拼写错误能静默扩大日志可见范围。

## 修复方案

- 写入端仅接受大小写不敏感的 `AND` / `OR`，缺省仍为 `AND`；字段名和值在拼接 LogsQL 前按字面量编码，`@timestamp`、含 `/` 等合法特殊字段使用双引号字段名，并拒绝可跳出旧引号/通配符上下文的语法字符。
- 读取端 `strict` 模式对未知值和 falsey 非对象规则 fail-closed，并在查询分组信息中标记 `invalid_rule`。
- 为已盘点且明确需要短期维持旧行为的历史分组提供按 ID 显式配置的兼容列表；只有列表内的历史未知字符串才按旧 `OR` 解释，并标记 `legacy_or`。
- 提供只读盘点命令，按稳定主键分批扫描，仅输出分组 ID、名称、创建人、组织范围和分类，不输出完整规则值。
- 首轮滚动升级前，先用新镜像 one-off 运行 `audit_log_group_rule_modes --target-enforcement legacy --fail-on-uncovered`，修正所有会逃逸旧 prefix/suffix 裸通配符上下文的存量规则；未通过不得进入 legacy 滚动窗口。随后将新版本设为 `LOG_GROUP_RULE_MODE_ENFORCEMENT=legacy`：新 writer 拒绝坏规则及 `*`、布尔连接、管道、括号和前导否定，新 reader 与旧 reader 保持相同语义。等旧 writer 全部排空后再按 strict 目标盘点，falsey 非对象及畸形结构必须修正，未知字符串必须修正或加入 `LOG_GROUP_LEGACY_OR_GROUP_IDS`。
- 安全字面量编码会修正旧查询语法（例如正则元字符、prefix/suffix），因此 `legacy` 到 `strict` **禁止滚动混部**：先冻结日志分组写入并停止搜索流量，排空在途搜索，运行 `audit_log_group_rule_modes --target-enforcement strict --fail-on-uncovered`，一次性让全部实例以 `strict` 启动后再恢复流量。
- 切回 `legacy` 同样须先冻结写入、停流排空，并运行 `audit_log_group_rule_modes --target-enforcement legacy --fail-on-uncovered`；strict 可安全表达但旧裸通配符会逃逸的规则必须先修正，否则禁止回滚。预检通过后一次性切换全部实例，不得混部；数据库无需逆向迁移。
- 切换 `strict` 后先把某分组修正为合法规则，再移除其兼容 ID。旧镜像只允许在上述 legacy 目标预检通过并整体切换后回滚。

## 测试方案

- 纯函数覆盖合法 AND/OR、缺省 AND、未知字符串和 falsey 非对象默认 deny-all、显式兼容 OR，以及 `legacy` 迁移模式的旧读语义。
- Serializer 覆盖 mode 与 conditions 非法输入拒绝和合法输入兼容。
- 真实数据库管理命令覆盖 keyset 分批、隐私输出和可用于发布预检的非零退出。
- 运行搜索构建最低真实 seam，证明同一规则在默认与显式兼容配置下分别得到 deny-all 和旧 OR。

## 已知限制

兼容列表不推断历史规则的原始意图，只保留已明确选中的分组的旧运行语义。`legacy` 模式和兼容列表都是迁移工具，不是长期配置；分组负责人确认并修正规则后应删除对应 ID。
