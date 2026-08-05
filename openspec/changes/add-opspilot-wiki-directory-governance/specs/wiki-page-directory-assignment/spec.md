## ADDED Requirements

### Requirement: 页面具有一个主目录和明确归类模式
目录能力启用后，active generation 中的每个知识页面 MUST 归属同一知识库中的且仅一个主目录，并 MUST 记录 `directory_assignment_mode=auto|manual`。`KnowledgePage.directory/current_version/status/assignment_mode` 只作为旧路径兼容镜像，活动读取以 `WikiGenerationPage` 为准。目录归属 MUST 与页面身份解耦，移动页面不得改变页面 ID 或版本链。

#### Scenario: 自动生成页面
- **WHEN** 构建创建一个具有合法目录路由的新页面
- **THEN** 页面 MUST 保存目标 `directory_id` 与 `auto` 模式
- **AND** 页面 ID、标题身份和版本历史 MUST 不依赖目录路径

#### Scenario: 人工移动页面
- **WHEN** 管理员把一个或多个页面移动到另一活动目录
- **THEN** 系统 MUST 更新目录、设置模式为 `manual` 并记录 `PageDirectoryChange`
- **AND** 页面正文、当前版本、证据和关系 MUST 保持不变

### Requirement: 人工归类锁定优先于自动路由
构建、资料更新、全量重建和结构 reconciliation MUST 保留 manual 页面当前目录，除非用户明确执行“恢复自动归类”。

#### Scenario: 重建遇到人工页面位置
- **WHEN** manual 页面在新构建结果中得到不同目录 key
- **THEN** 系统 MUST 保留人工目录并仅在构建追踪中记录建议差异
- **AND** 系统 MUST 不创建目录审批项

#### Scenario: 恢复自动归类
- **WHEN** 管理员对 manual 页面执行恢复自动归类
- **THEN** 系统 MUST 将模式改为 `auto`，按当前 active structure revision 立即重新执行确定性路由
- **AND** 没有合法目标时页面 MUST 进入待归类

### Requirement: 自动归类使用确定性优先级
服务端 MUST 按以下顺序确定页面目录：保留已有 manual 目录、采用当前 revision 与本批 classification root 中合法的 LLM `directory_key`、采用同一范围内 `page_type` 的唯一配置默认目录、采用允许接收页面的 classification root、回退系统待归类。后续条件不得覆盖前一条件；结构校验 MUST 拒绝同一有效范围内一个 page type 存在多个默认目录。

#### Scenario: LLM 返回合法 key
- **WHEN** auto 页面生成结果包含当前 revision 中活动且允许接收页面的 `directory_key`
- **THEN** 系统 MUST 将页面归入该目录，并在构建追踪中保存 key、理由和模型置信度

#### Scenario: LLM 返回未知 key
- **WHEN** 生成结果包含不存在、已退役、已合并或属于其他知识库的 key
- **THEN** 系统 MUST 不自动创建目录，并继续尝试同一 classification root 范围内的类型默认目录、允许接收页面的 classification root 或待归类
- **AND** 单页路由失败 MUST 不导致整份资料构建失败

#### Scenario: classification root 与已有 manual 页面
- **WHEN** 批次指定 classification root，但已命中的 manual 页面位于该子树外
- **THEN** 系统 MUST 保留 manual 目录；classification root 只约束该批次的 auto 建议和 fallback

#### Scenario: 类型默认目录位于 classification root 外
- **WHEN** auto 页面无法采用合法 LLM key，且全局类型默认目录不在批次子树内
- **THEN** 系统 MUST 忽略越界默认，改用允许接收页面的 root 或待归类

#### Scenario: merged key 的不同来源
- **WHEN** 当前 LLM 输出 merged/retired key
- **THEN** 系统 MUST 把它视为非法建议并执行 fallback
- **AND** 只有原生导入、历史链接或审计读取 MAY 跟随持久 merged redirect 到活动目标，并记录发生了 redirect

#### Scenario: 持久 redirect 的活动目标不符合当前路由上下文
- **WHEN** 原生导入、历史链接或审计读取跟随持久 merged redirect 到活动目标，但目标位于当前 classification root 外或拒绝页面的 `page_type`
- **THEN** 系统 MUST 记录 `out_of_scope_key` 或 `schema_mismatch`，不采用该目标并继续执行确定性 fallback
- **AND** 该上下文不匹配 MUST 不被误报为 redirect 结构损坏

#### Scenario: 持久 redirect 结构损坏
- **WHEN** 持久 redirect 缺少目标、形成循环、跨知识库、指向非活动目录或指向不允许接收页面的目录
- **THEN** 系统 MUST 失败关闭并报告结构错误，不得静默采用目标或把损坏链当作普通 fallback

### Requirement: page type 合法域由固定 structure revision 冻结
每个 structure revision MUST 保存完整且显式的 `page_types` 合法域；目录的 `allowed_page_types` 与 `default_for_page_types` 只能引用该域。构建、导入、重建和回退 MUST 使用任务开始时固定 revision 的同一快照，不得从目录规则并集反推类型域，也不得在任务中回读后来变化的 `schema_md`。

#### Scenario: 目录规则引用类型域外的值
- **WHEN** 管理员保存的结构让 `allowed_page_types` 或 `default_for_page_types` 引用固定 revision 的 `page_types` 域外值
- **THEN** 服务端 MUST 拒绝整个结构保存并返回可定位的校验错误

#### Scenario: auto 页面类型为空白或未知
- **WHEN** auto 页面输出空白 `page_type` 或不在固定 revision `page_types` 域中的值
- **THEN** 系统 MUST 记录 schema mismatch，跳过 LLM key、类型默认和 classification root，并把页面路由到系统待归类
- **AND** 系统 MUST 保留已生成正文且不创建目录审批项

#### Scenario: manual 页面类型为空白或未知
- **WHEN** manual 页面当前 `page_type` 为空白或不在固定 revision 的合法域中
- **THEN** 系统 MUST 保留其人工目录并记录 schema mismatch，不得由构建覆盖人工归类

### Requirement: LLM 路由输出受到结构契约约束
生成提示 MUST 包含固定 structure revision 的目录 key、名称、层级、说明和允许规则；LLM MUST 输出结构化 `directory_key`，不能把自由文件路径作为领域契约。服务端 MUST 在持久化前重新执行确定性校验。

#### Scenario: 输出与页面类型规则冲突
- **WHEN** LLM 选择的目录违反当前 revision 对 page type 或内容用途的硬规则
- **THEN** 服务端 MUST 拒绝该 key、应用确定性 fallback 并记录 schema mismatch
- **AND** 系统 MUST 不直接丢弃已生成页面正文

### Requirement: 页面标题在知识库内全局唯一
系统 MUST 对同一知识库的所有页面状态执行规范标题唯一约束，包括 active、archived、pending 和 source-invalid 页面；不同知识库可以存在相同标题。规范化算法 MUST 固定为 Unicode NFKC、去除首尾空白、把连续 Unicode 空白折叠为一个空格，并以 casefold 值比较；持久化标题保留清理后的展示大小写。创建、改名、导入、构建和重建 MUST 在知识库行锁下使用同一算法，数据库 `(knowledge_base,title)` 唯一约束作为最终并发后盾。

#### Scenario: 新结果命中活动页面
- **WHEN** 构建、导入或人工创建产生与同知识库活动页面相同的规范标题
- **THEN** 系统 MUST 复用或更新该页面身份，不能创建第二个页面

#### Scenario: 新结果命中归档页面
- **WHEN** 新生成结果与同知识库归档页面标题相同且身份无歧义
- **THEN** 系统 MUST 恢复并复用归档页面 ID，再创建新的候选或当前版本

#### Scenario: 并发创建相同标题
- **WHEN** 两个请求并发在同一知识库创建相同规范标题
- **THEN** 数据库唯一约束和领域服务 MUST 保证最多存在一个页面，并向失败请求返回可解释冲突

#### Scenario: Unicode、空白或大小写等价标题
- **WHEN** 同一知识库已有 `Ａ  Guide`，新入口提交经 NFKC、空白折叠与 casefold 后等价的标题
- **THEN** 统一身份服务 MUST 把它识别为同一标题身份，不能依赖数据库 collation 产生不同结果

#### Scenario: 页面改名
- **WHEN** 管理员把页面改为知识库内唯一的规范标题
- **THEN** 系统 MUST 保留页面 ID，通过轻量 governance generation 发布新标题与派生 WikiLink/关系结果
- **AND** v1 不创建旧标题 alias；这一限制 MUST 在影响提示中明确


#### Scenario: 页面身份冲突重试
- **WHEN** 同一知识库对同一规范标题身份重复创建开放页面身份冲突
- **THEN** adapter MUST 以“知识库 ID + 规范标题键”作为唯一稳定幂等键并返回既有开放记录
- **AND** `page_type`、目录、来源、build/generation、理由和操作者 MUST 不参与该键

#### Scenario: adapter 收到未规范化标题键
- **WHEN** 页面身份冲突 adapter 收到未经过统一 NFKC、空白折叠与 casefold 算法的标题键
- **THEN** adapter MUST 拒绝输入，不得静默规范化或沿用仍包含 `page_type` 的旧决策签名

### Requirement: page type 与目录承担不同职责
`page_type` MUST 继续描述内容类型和生成规则，但 MUST 不再作为知识列表的层级身份或唯一分组依据。同一 page type 可以分布在多个目录，同一目录可以按结构规则容纳多个 page type。

#### Scenario: 同类型页面分布在不同目录
- **WHEN** 两个 `procedure` 页面依据用途分别归入部署目录和故障目录
- **THEN** 系统 MUST 保留相同 page type 和不同主目录，并能分别按类型或目录筛选

### Requirement: 人工创建和候选流程遵守目录与标题约束
在具体目录下人工新建页面 MUST 设置 manual；从“全部知识”新建 MUST 要求选择目录或明确选择待归类。与已有标题冲突的候选 MUST 关联已有页面及候选版本，不能创建重复 `KnowledgePage`。

#### Scenario: 在目录中创建页面
- **WHEN** 用户在活动目录上下文中手工创建唯一标题页面
- **THEN** 页面 MUST 归入当前目录并设置 `manual`

#### Scenario: 候选标题已存在
- **WHEN** human/mixed 冲突或 QA 候选使用已有页面标题
- **THEN** 系统 MUST 把候选正文保存为关联已有页面的非当前版本/检查项
- **AND** 页面表中 MUST 仍只有一个该标题身份

### Requirement: 只有真实业务歧义产生非阻塞候选
新 AI 页面和可确定更新 MUST 自动进入 generation；只有 human/mixed 正文冲突或无法确定唯一页面身份时才能创建非阻塞候选。目录低置信度、未知 key 或 Schema mismatch MUST 通过待归类和构建追踪处理，而不是审批。

#### Scenario: 新 AI 页面
- **WHEN** 生成了唯一标题且目录可确定或可回退的新 AI 页面
- **THEN** 系统 MUST 自动纳入候选 generation，不创建采纳审批

#### Scenario: 人工正文冲突
- **WHEN** incoming 正文会覆盖 human/mixed 页面且系统无法确定合并结果
- **THEN** 系统 MUST 保留当前正文、创建非阻塞候选并允许构建其余页面继续

### Requirement: 正文冲突候选使用稳定内容身份幂等创建
正文冲突开放记录的 v1 稳定键 MUST 仅由 `knowledge_base_id`、`page_id`、`locked_current_version_id`、`content_contract_fingerprint` 和按 `(material_id, content_hash)` 排序去重的非空完整来源集合组成，并 MUST 以版本化 canonical JSON 的 SHA-256 digest 持久化。`candidate_body` 或其 hash、build/generation ID、reason、operator、page type、目录、归类建议、confidence、locator、参与者顺序和 candidate version ID MUST 不参与该键。

#### Scenario: 同一正文冲突构建重试
- **WHEN** 重试具有相同锁定当前版本、内容契约和来源内容身份的正文冲突，但 build/generation、候选措辞、理由或操作者发生变化
- **THEN** adapter MUST 在创建新的 `PageVersion` 前按稳定 digest 返回既有开放候选并设置 `created=false`
- **AND** 系统 MUST 不替换该开放候选已冻结的正文

#### Scenario: 正文冲突身份边界变化
- **WHEN** 锁定当前版本、内容契约指纹或任一来源的 material ID/content hash 发生变化
- **THEN** 系统 MUST 计算不同稳定 digest，不得复用旧开放候选
- **AND** 旧候选 MUST 由既有过期生命周期关闭，而不是改写为新输入
