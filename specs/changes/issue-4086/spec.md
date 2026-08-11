# Spec — Issue #4086 日志分组规则模式收敛

## 根因

日志分组 `rule` 是无结构 `JSONField`。写入边界不校验 `mode`，读取边界只特判 `AND`，其余字符串都按 `OR` 执行，导致拼写错误能静默扩大日志可见范围。

## 修复方案

- 写入端仅接受大小写不敏感的 `AND` / `OR`，缺省仍为 `AND`。
- 读取端 `strict` 模式对未知值和 falsey 非对象规则 fail-closed，并在查询分组信息中标记 `invalid_rule`。
- 为已盘点且明确需要短期维持旧行为的历史分组提供按 ID 显式配置的兼容列表；只有列表内的历史未知字符串才按旧 `OR` 解释，并标记 `legacy_or`。
- 提供只读盘点命令，按稳定主键分批扫描，仅输出分组 ID、名称、创建人、组织范围和分类，不输出完整规则值。
- 滚动升级先将新版本设为 `LOG_GROUP_RULE_MODE_ENFORCEMENT=legacy`：新 writer 已拒绝坏规则，新 reader 与旧 reader 保持相同语义；等旧 writer 全部排空后再盘点。falsey 非对象规则必须修正，未知字符串必须修正或加入 `LOG_GROUP_LEGACY_OR_GROUP_IDS`；`audit_log_group_rule_modes --fail-on-uncovered` 通过后才滚动切换 `strict`。
- 切换 `strict` 后先把某分组修正为合法规则，再移除其兼容 ID。回滚前重新运行严格预检；未覆盖项为零时可先切回 `legacy` 再回滚旧镜像，数据库无需逆向迁移。

## 测试方案

- 纯函数覆盖合法 AND/OR、缺省 AND、未知字符串和 falsey 非对象默认 deny-all、显式兼容 OR，以及 `legacy` 迁移模式的旧读语义。
- Serializer 覆盖 mode 与 conditions 非法输入拒绝和合法输入兼容。
- 真实数据库管理命令覆盖 keyset 分批、隐私输出和可用于发布预检的非零退出。
- 运行搜索构建最低真实 seam，证明同一规则在默认与显式兼容配置下分别得到 deny-all 和旧 OR。

## 已知限制

兼容列表不推断历史规则的原始意图，只保留已明确选中的分组的旧运行语义。`legacy` 模式和兼容列表都是迁移工具，不是长期配置；分组负责人确认并修正规则后应删除对应 ID。
