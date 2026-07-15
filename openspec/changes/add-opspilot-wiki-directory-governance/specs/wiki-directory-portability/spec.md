## ADDED Requirements

### Requirement: 来源文件夹只表示 provenance
资料 MUST 保存完整 `source_relative_path`、稳定 `source_identity`、`source_folder_path` 和 `content_hash`。来源文件夹可以作为 LLM 分类上下文，但 MUST 不自动创建、重命名或决定知识目录。

#### Scenario: 两个文件夹包含同名资料
- **WHEN** `project-a/config.yaml` 与 `project-b/config.yaml` 被上传到同一知识库
- **THEN** 系统 MUST 以完整相对路径区分来源身份，并在证据中保留各自 provenance
- **AND** 两者 MUST 不因 basename 相同而覆盖缓存或来源记录

#### Scenario: 来源文件夹不存在于知识结构
- **WHEN** 上传 ZIP 包含此前未知的多层物理文件夹
- **THEN** 系统 MUST 仅保存来源路径并使用现有结构分类
- **AND** 默认不得把物理文件夹转换为知识目录

### Requirement: 批次可限制在知识目录子树中归类
上传或导入操作 MAY 指定 `classification_root_directory`，系统 MUST 将该批次的自动分类候选限制在目标目录及其活动后代；该选项不能改变全局结构。

#### Scenario: 指定分类根目录
- **WHEN** 用户在“产品知识”目录上传一批资料并选择限制到当前子树
- **THEN** LLM 提示和确定性校验 MUST 只暴露该子树可选 key
- **AND** 无合法子目录时页面 MUST 回退到目标根目录或待归类，而不是越界归档

### Requirement: 原生导出包含机器可往返 manifest
知识库原生导出 MUST 包含 `manifest.json`、`structure.json` 和按人类可读目录展示路径组织的 Markdown 页面。manifest MUST 保存格式版本、知识库身份、结构 revision/hash、完整目录节点及稳定 key/parent/order/status、空目录、页面到目录/文件映射和导出时间。

#### Scenario: 导出含空目录的知识库
- **WHEN** 知识库包含空活动目录和多层页面
- **THEN** 导出包 MUST 在 structure/manifest 中保留空目录和完整层级
- **AND** 每个页面 Markdown frontmatter MUST 至少包含 title、page_type、directory_key 和 tags

#### Scenario: 目录重命名后导出
- **WHEN** 同一稳定目录被重命名后再次导出
- **THEN** 展示文件路径 MAY 变化，但 manifest 中 directory key MUST 保持不变

### Requirement: 原生导入按稳定身份恢复目录
导入 OpsPilot 原生归档时，目录匹配 MUST 按 `directory_key`、manifest 映射、用户选择目标、同一 classification root 范围内的 page type 默认目录、允许接收页面的 classification root、待归类的顺序执行。只有新建/空知识库在管理员确认“恢复归档结构”后，系统导入器才能校验并使用 manifest 稳定 key 准备首个业务 structure revision 与 staging generation，并通过 base generation 和 active structure revision CAS 原子激活二者；非空知识库的未知或退役 key MUST 不自动创建目录。

#### Scenario: 导入相同结构 revision 的原生归档
- **WHEN** manifest 中的目录 key 在目标知识库均合法可用
- **THEN** 页面 MUST 按 key 恢复主目录，且物理 ZIP 路径不能覆盖 manifest 映射

#### Scenario: 导入到新建或空知识库
- **WHEN** 管理员在仅含系统待归类目录的目标知识库确认恢复原生归档结构
- **THEN** 系统 MUST 把归档视为不可信输入，先校验格式、key 语法与唯一性、父子关系、深度、名称、系统保留 key 和资源配额，再准备首个业务 structure revision 与 staging generation，并仅在 base generation 和 active structure revision CAS 均成功时原子激活二者
- **AND** 这些 key 只能由受控的原生导入服务在空知识库中写入，界面不得暴露为用户可编辑的原始 ID/key

#### Scenario: manifest 引用未知 key
- **WHEN** 页面引用目标知识库不存在的 key
- **THEN** 预检查 MUST 报告未知 key，并按显式目标、同一 classification root 范围内的类型默认目录、允许接收页面的 classification root 或待归类回退

### Requirement: 第三方归档默认不创建知识目录
导入非 OpsPilot 原生归档时，系统 MUST 按用户选择目标、ZIP 路径映射到现有目录、同一 classification root 范围内的 page type 默认目录、允许接收页面的 classification root、待归类的顺序归档。只有用户显式启用“从文件夹创建人工目录”并确认预览时，系统才能创建目录。

#### Scenario: 默认导入第三方 ZIP
- **WHEN** 第三方 ZIP 包含 `docs/api/v1/page.md` 且目标知识库没有对应目录
- **THEN** 系统 MUST 不创建 `docs/api/v1` 目录链，并把页面路由到后续 fallback

#### Scenario: 显式从文件夹创建目录
- **WHEN** 管理员启用该选项且预览通过名称、深度、冲突和数量校验
- **THEN** 系统 MUST 通过结构治理服务准备新的 structure revision 与 governance generation，并仅在 base generation 和 active structure revision CAS 均成功时原子激活二者；激活成功后才启动页面导入
- **AND** 任一结构创建失败 MUST 阻止页面导入开始

### Requirement: 导入执行前提供完整预检查
导入预检查 MUST 返回新页面数、可更新页面数、标题冲突、未知 key、未映射路径、非法标题、重复文件、目录深度和安全限制结果。预检查不得修改知识库，并 MUST 签发短期、单次使用的 execute token，绑定 archive hash、knowledge base、操作者、目标目录、`structure_version`、`base_generation_id`、导入选项和配额版本；执行时 MUST 重新鉴权并复验全部绑定值。

#### Scenario: 预检查发现多个问题
- **WHEN** 归档同时包含重复标题、未知 key 和超深路径
- **THEN** API MUST 一次返回所有可检测问题及对应文件，不得在首个错误后静默停止
- **AND** 未经用户修复或确认允许 fallback 前不得执行导入

#### Scenario: 预检查后结构或输入变化
- **WHEN** execute 时归档 hash、操作者、知识库、目标、`structure_version`、`base_generation_id`、导入选项或配额与 token 任一绑定值不同
- **THEN** 系统 MUST 拒绝执行并要求重新 preflight，不得沿用旧目录映射

#### Scenario: execute token 被重复使用
- **WHEN** 已成功或已开始执行的 token 再次提交，或 token 已过期
- **THEN** 系统 MUST 拒绝 replay，且不能重复创建 revision、页面版本或 generation

### Requirement: 标题冲突遵守页面贡献边界
导入与已有标题冲突时 MUST 复用同一页面身份。AI 页面可以按明确策略批量自动更新；human/mixed 页面正文冲突 MUST 保留当前正文并创建候选，不能自动覆盖。

#### Scenario: 导入更新 AI 页面
- **WHEN** 原生归档页面唯一命中已有 AI 页面且输入版本合法
- **THEN** 系统 MUST 创建新的候选 generation 版本并保留页面 ID

#### Scenario: 导入冲突 human 页面
- **WHEN** 导入正文不同且命中 human/mixed 页面
- **THEN** 系统 MUST 保持当前正文并在预检查/结果中创建非阻塞候选说明

### Requirement: ZIP 与 Markdown 导入执行安全校验
系统 MUST 防御 zip-slip、绝对路径、驱动器路径、符号链接、控制字符、非法 Unicode 规范化碰撞、超限文件大小、总大小、文件数和目录深度，并 MUST 在读取或写入前验证知识库授权。

#### Scenario: ZIP 路径穿越
- **WHEN** 归档条目路径包含绝对路径或规范化后的 `..` 越界
- **THEN** 系统 MUST 拒绝整个导入且不得在目标临时目录或知识库外写文件

#### Scenario: Unicode 文件名碰撞
- **WHEN** 两个文件名经系统规范化后映射为同一页面文件身份
- **THEN** 预检查 MUST 报告碰撞并阻止无提示覆盖

### Requirement: 导入后维护非向量消费面
导入 generation 激活后，系统 MUST 更新页面版本、目录历史、WikiLink、PageRelation、图谱、目录计数和关键词消费面；本变更 MUST 不触发向量生成或清理。

#### Scenario: 导入成功
- **WHEN** 导入 generation 完成并通过一致性校验
- **THEN** 页面列表、关键词筛选和图谱 MUST 同时可见新页面及目录
- **AND** 既有 embedding 与 PageChunk 向量字段 MUST 不因目录导入被重写
