## ADDED Requirements

### Requirement: 结构化目录配置是机器真相
系统 MUST 使用结构化目录配置的完整快照驱动目录树、页面归类和构建校验；`schema_md` MUST 仅作为用途说明与生成规则上下文，不能覆盖结构化配置中的目录身份、父子关系、顺序或状态。

#### Scenario: 保存合法结构
- **WHEN** 有知识库管理权限的用户提交完整结构快照和当前 `structure_version`
- **THEN** 系统 MUST 自动完成确定性校验、创建不可变 revision 与基于当前知识快照的轻量 governance generation，并原子激活相互绑定的 structure revision 和 generation
- **AND** 保存流程 MUST 不创建草稿、审批或人工验证步骤

#### Scenario: 保存非法结构
- **WHEN** 提交的结构包含重复 key、跨知识库父节点、循环、超过最大深度、重复同级名称或非法系统目录变更
- **THEN** 系统 MUST 整体拒绝保存并返回可定位到节点的错误
- **AND** 当前 active revision 与目录树 MUST 保持不变

### Requirement: 目录具有稳定的系统身份
每个目录 MUST 具有系统生成的数据库 ID 和知识库内唯一、不可复用的稳定 key。用户界面 MUST 不要求用户填写原始 ID；LLM、导入导出和历史重定向 MUST 使用稳定 key 而不是展示路径作为机器身份。

#### Scenario: 创建目录
- **WHEN** 管理员在结构编辑器中创建目录
- **THEN** 系统 MUST 生成目录 ID 与稳定 key，并保存名称、父节点、排序、来源和状态
- **AND** 后续重命名、移动或重排 MUST 保持 ID 与 key 不变

#### Scenario: 完整快照提交已有与新增节点
- **WHEN** UI 提交结构编辑结果
- **THEN** 已有节点 MUST 回传服务端先前返回的只读 ID/key，服务端 MUST 校验二者未被替换
- **AND** 新节点 MUST 只提交 `client_ref` 和业务属性，不能选择 ID/key；成功响应返回 client_ref 到系统 ID/key 的映射

#### Scenario: 防止路径身份耦合
- **WHEN** 目录被重命名或移动到另一父目录
- **THEN** 已归属页面、导入映射和外部引用 MUST 继续通过目录 ID/key 指向同一目录
- **AND** 系统 MUST 不把新展示路径解释为新目录身份

### Requirement: 目录树满足结构不变量
系统 MUST 保证目录的父节点属于同一知识库、目录不能成为自身祖先、层级深度不超过 8，并对活动目录执行同一父节点下的规范化名称唯一约束。

#### Scenario: 阻止循环移动
- **WHEN** 管理员尝试把目录移动到自身或任一后代下
- **THEN** 系统 MUST 拒绝整个结构保存并返回循环路径

#### Scenario: 不同分支允许同名目录
- **WHEN** 两个规范化名称相同的目录位于不同父节点下
- **THEN** 系统 MUST 允许保存，并继续以稳定 ID/key 区分它们

### Requirement: 每个知识库具有不可变的待归类目录
系统 MUST 为每个知识库创建且仅创建一个系统“待归类”目录。该目录 MUST 可接收页面，但不能被重命名、移动、排序到普通目录内部、合并、退役或删除。

#### Scenario: 初始化知识库
- **WHEN** 新知识库创建或存量知识库执行目录 bootstrap
- **THEN** 系统 MUST 幂等创建系统待归类目录并将其纳入结构读取结果

#### Scenario: 修改系统目录
- **WHEN** 用户提交任何改变待归类目录身份、名称、父节点或状态的操作
- **THEN** 系统 MUST 拒绝操作，且不得产生新 revision

### Requirement: 人工目录治理形成不可变 revision 与审计
目录新增、重命名、移动、排序、合并、退役和归档 MUST 通过知识库级授权执行，并 MUST 记录操作者、前后结构版本、影响摘要和时间。v1 MUST 不引入目录级 ACL。

#### Scenario: 保存多项结构调整
- **WHEN** 管理员在一次编辑会话中新增、重命名和重排多个目录后保存
- **THEN** 系统 MUST 将这些调整作为一个原子结构 revision 激活
- **AND** 审计记录 MUST 能还原该 revision 的完整树和节点差异

#### Scenario: 普通知识库成员编辑结构
- **WHEN** 只有知识库读取权限的成员调用结构写接口
- **THEN** 系统 MUST 返回权限错误且不得修改任何节点或 revision

### Requirement: 结构写入使用乐观锁与短事务
所有结构写操作 MUST 携带客户端读取时的 `structure_version` 与 `base_generation_id`，并在有界事务内锁定知识库、复验两个 active 指针、写入节点状态和激活相互绑定的新 revision/governance generation。已激活 revision 与 generation 不得原地改写。

#### Scenario: 两个管理员并发保存
- **WHEN** 管理员 A 先以版本 N 保存成功，管理员 B 随后仍以版本 N 保存
- **THEN** B 的请求 MUST 返回 `409 structure_version_conflict`
- **AND** 系统 MUST 不静默合并或覆盖 A 的 revision

### Requirement: 目录合并是纯结构操作
目录合并 MUST 只移动源目录的页面和子目录归属，不得调用 LLM 合并页面正文。系统 MUST 在执行前返回影响预览与短期单次 operation token，绑定 knowledge base、structure version、base generation、源/目标/动作参数和影响 hash；执行时 MUST 重新鉴权、复验绑定值并重算影响。发现同名子目录冲突或预览后状态变化时，v1 MUST 中止整个合并。

#### Scenario: 无冲突合并
- **WHEN** 管理员确认把源目录合并到同知识库目标目录且不存在同名子目录冲突
- **THEN** 系统 MUST 原子移动页面与子目录，将源目录标记为 `merged` 并记录 `merged_into`
- **AND** 源 key 与历史展示路径 MUST 保留持久 redirect/tombstone
- **AND** 被移动页面 MUST 保持原 `auto|manual` 归类模式，并记录来源为结构合并的目录变更历史

#### Scenario: 子目录冲突
- **WHEN** 源目录和目标目录包含规范化名称相同的活动子目录
- **THEN** 系统 MUST 在预览中列出冲突并拒绝执行任何移动

#### Scenario: 预览后页面或结构变化
- **WHEN** 合并执行时 active structure、base generation、源/目标参数或影响 hash 与 operation token 不一致
- **THEN** 系统 MUST 拒绝旧 token 并要求重新预览，不得按过期影响集合执行

### Requirement: 目录删除与退役不隐式删除知识
非空目录 MUST 不能直接删除。空人工目录可以归档；结构化配置移除的目录 MUST 标记为 `retired`；任何目录操作 MUST 不隐式删除页面正文、版本、证据或关系。

#### Scenario: 删除非空目录
- **WHEN** 管理员请求删除包含直属页面、后代页面或活动子目录的目录
- **THEN** 系统 MUST 拒绝删除并返回直属/递归页面数和子目录数

#### Scenario: 配置移除目录
- **WHEN** 新结构 revision 不再包含此前由 Schema 骨架创建的目录
- **THEN** 系统 MUST 将目录标记为 `retired` 并保留稳定身份和历史
- **AND** 目录中的页面 MUST 先迁移到明确目标或待归类，不能级联删除
- **AND** 含页面的退役请求 MUST 提供迁移目标映射并与 revision 原子执行；页面原归类模式保持不变，未提供映射时整体拒绝
