# OpsPilot Wiki 固定结构、OKF 优先导入与问答出图

Status: ready

## Problem Statement

知识库管理员现在要在「设置 → 用途与结构」里维护两份 Markdown（Purpose / Schema），还要在新建时从五套模板里选一套决定根目录。这些内容多数人不会认真写，写了也只影响构建提示词，却让「简介」和「用途」变成两个互相不同步的字段。

目录结构可被模板、Schema 同步和导入任意改写。导入 OKF bundle 时只拿压缩包第一层文件夹名去对根目录，GitHub 下载包或 `test/llm_wiki/` 这类多层包装一律对不上，整包进「未分类」；已有一堆知识后再导入，目录和知识散落在两处，用户看不出哪里是「实体」哪里是杂项。

同时还存在「导入 Markdown ZIP」这条与 OKF 并行的知识捷径，三种归档种类各有一套目录路由和冲突规则，与 OKF 的规则互相干扰。

问答只返回文本。资料里的截图（操作步骤、界面指引）已经解析落盘，但用户在答案里看不到，只能点开引用抽屉再找。

## Solution

知识库结构固定为 llm_wiki 风格的六个根：五个知识根「实体 / 概念 / 待研究问题 / 对比 / 综合」，加一个只放原始资料的「来源」。这六个根不可删、不可改名；用户和导入仍可在根上新增同级目录。

「用途与结构」页签和模板选择去掉。简介必填、纯文本，直接作为构建与 Overview 的辅助上下文。

批量知识导入只保留 OKF。导入时自动剥掉纯包装层，找到第一个真正承载知识的层作为导入层；导入层里与六根同名的文件夹并入对应根，其它文件夹在根上新建同级；本层若已有散落知识页则整层进一个新建根。导入后与资料构建一样补一次语义 Overview。

资料解析构建保留：MarkItDown 解析成来源 md，再由 LLM 分解成知识页，按页面类型进五个知识根。构建出的页从出生起带完整 OKF 元数据（含 `sources` 溯源），导出不再合成。

问答时进入上下文的知识页附带其正文图，以及关联资料解析 md 中命中片段附近的图，模型可在答案中按需引用。

## User Stories

1. As a 知识库管理员, I want 新建知识库时只填名称、简介、模型和组织, so that 不用再理解 Purpose / Schema Markdown 或挑模板。
2. As a 知识库管理员, I want 简介必填并作为构建提示的辅助上下文, so that 一句「目标 + 收录范围」就能引导分解出什么页。
3. As a 知识库使用者, I want 任何知识库打开都是同样的六个根目录, so that 跨库浏览和问答路由有一致预期。
4. As a 知识库管理员, I want 导入 `test/llm_wiki/实体|测试/…` 或 GitHub 下载包时包装层被自动剥掉, so that 「实体」下的知识进知识库「实体」，「测试」成为根上同级目录，而不是全部进未分类。
5. As a 知识库管理员, I want 包装层里若混有散落知识页（如 `IT/目录介绍.md` + `IT/wiki/`）时整层进一个新建根 `IT`, so that 介绍页不会被当作壳剥丢。
6. As a 知识库管理员, I want 已有一堆知识后再导入 OKF，index 与目录概览反映合并后的全量, so that 检索和路由不会指向旧结构。
7. As a 知识库管理员, I want 纯 OKF 库的「来源」目录是空的并有提示, so that 我知道这里只会出现上传的资料。
8. As a 知识库管理员, I want 资料构建出的知识页直接能导出为带 `sources` 的 OKF concept, so that 导入 → 导出 → 再导入无损，且外部能看到每页来自哪份资料。
9. As a 知识库使用者, I want 问操作类问题时答案里能看到来源里的截图, so that 不必再点开引用抽屉找图。
10. As a 知识库管理员, I want 存量库自动补齐六个根、简介为空时从旧 Purpose 回填, so that 不用手工重建就能用新规则导入和构建。

## Implementation Decisions

### 结构冻结

- 冻结根为六个：`entity` 实体、`concept` 概念、`query` 待研究问题、`comparison` 对比、`synthesis` 综合，以及资料根「来源」。前五个是知识根（页面类型与目录一一对应），「来源」不接受知识页，只挂原始资料。
- 冻结根 `origin` 标为 `system`，与「待归类」同等保护：不可删除、不可改名、不可移出根、结构保存时不可省略。「待归类」保留为系统目录。
- 允许在根上新建同级目录（手工或导入产生），也允许在任意目录下建子目录；这些目录 `origin` 为 `manual` 或导入来源，可正常治理。
- `source` 页面类型停止使用：不再生成 `source` 类型知识页，结构 `page_types` 收敛为五个。
- 模板机制下线：模板列表端点、`generate_purpose_schema` 端点、Schema Markdown → 目录同步全部移除。`template_key` 字段保留仅作记录，新库固定写 `general`。所有新库 bootstrap 出的都是六根 + 待归类。

### 简介与 Purpose

- `introduction` 必填（创建与更新均校验非空），纯文本 `TextArea`，不渲染 Markdown、不限长。
- 构建 Stage1/Stage2 提示词与 Overview 确定性文本中原本注入 `purpose_md` 的位置一律改为注入 `introduction`；为空的情形不再出现。
- `purpose_md` / `schema_md` 停止在序列化器暴露、停止在任何写路径写入、停止在任何读路径读取；模型字段保留，避免迁移风险。
- 设置页只剩「基础信息」与「危险区」两个区块；新建弹窗去掉模板选择及用途 / 结构编辑。

### 存量迁移

- 一次性数据迁移：对每个知识库补齐缺失的冻结根（含「来源」），已有目录原样保留、不删不挪；`introduction` 为空时用 `purpose_md` 首个非标题段落去掉 Markdown 标记后回填，仍为空则写知识库名。迁移后需要激活一次新的结构修订，使 active structure 含六根。
- 老模板产生的非冻结根（如「问答」「操作步骤」）继续作为普通目录存在。

### 导入：只保留 OKF

- 批量知识导入唯一入口为「导入 OKF」。预检/执行端点仅接受 `import_format="okf"`；缺省或其它值返回 400，错误码 `import_format_unsupported`。
- 删除 `markdown` / `third_party` / `native` 三种归档种类的专属逻辑：格式嗅探、`path_mappings`、`restore_structure`、`folder_directory_name_conflict`、第三方文件夹预览等，及其专属前端文案与测试。前端去掉「导入 Markdown」按钮与 `importFormat` 分支，导入弹窗只剩 OKF 形态。
- OKF 与被删分支共用的安全边界（ZIP 校验、一次性 token / CAS、预检指纹、体积上限）以及导入后置链路（冲突 candidate + CheckItem、`[[wikilink]]` 关系重建、口语别名增强、图片落盘与覆盖导入 GC、`meta_snapshot.okf` 元数据、标题消歧）全部保留，不得删除。
- OKF 导出保留不变，作为唯一交换格式的出口。

### 导入：剥壳与导入层

- 从包顶开始逐层判断。忽略以下成员再数「有效目录」：`index.md`、`log.md`、`assets`、`__MACOSX`、`.git` 及隐藏目录。本层满足「有效目录恰好一个 **且** 没有可导入的知识 md」时视为纯包装层，剥掉并下钻；否则停止，当前层即导入层。
- 停止条件包括：有效目录 ≥ 2；唯一有效目录名恰好是六根之一的显示名（避免钻进「实体」）；本层存在可导入知识 md。
- 剥壳结果 `bundle_root` 回显到预检摘要，替代原「只剥一层唯一顶目录」逻辑。被剥掉层中的 `index.md` / `log.md` 继续按保留文件跳过；不会出现知识 md 被剥丢的情况，因为有知识 md 的层不会被剥。

### 导入：导入层对齐

- 导入层内的每个文件夹与六根 **显示名** 比对，大小写不敏感、NFKC 规范化；英文 `entity` 等不视为同名。命中的文件夹整棵并入对应根，其下层级原样保留；多个同名文件夹并入同一根。
- 未命中的文件夹在知识库根上新建同级目录（同名复用）。导入层整层无任一命中时，新建一个以导入层文件夹名命名的根，整树挂入。
- 导入层因存在散落知识 md 而停止时，本层所有内容（散页与所有子文件夹）进新建根，不再向下提升子树内的同名文件夹。
- 包内名为「来源」的文件夹按普通知识目录处理，不并入资料根。
- 页面 `page_type` 仍来自 frontmatter `type` 的映射；目录归属以文件夹对齐结果为准，两者不一致时文件夹赢。「按文件夹建目录」开关保留、默认开；关闭时页面按 `type` 进对应知识根，对不上进「概念」。
- 原「只对齐第一层到结构根」与「未命中进待归类」两条规则废止。

### 导入：导航产物

- index entry 与确定性 Overview 由 generation 激活时全量重算，导入后自然覆盖合并后的全量；不新增独立的 index 重建机制。
- OKF 导入执行成功后追加一次有界的语义 Overview 增强，与资料构建使用同一预算与调用约束；失败只记日志，不阻断导入、不回滚 generation。

### 资料解析与构建

- 资料上传、MarkItDown 解析、来源 md 落盘、LLM 分解构建全部保留。分解输入是来源 md，不是原始文件。
- 构建出的知识页按 `page_type` 进五个知识根；无类型或未知类型进「概念」。不按资料路径或来源文件夹建目录。
- 「来源」根只挂资料及其解析 md 预览；资料删除级联不变。纯 OKF 库「来源」为空，前端给空态提示。

### 构建产物原生 OKF

- `stage_ai_page` 为资料构建页写入 `meta_snapshot.okf`：`type`（=page_type）、`title`、`concept_id`、`description`（=summary）、`tags`、`generated{by: 模型名, at}`、`sources[{resource: 资料显示名, material_id}]`。字段由系统填充，不让 LLM 输出 YAML。
- `concept_id` 在页面首次创建时按当时目录显示名链 + slug 生成，此后挪目录、改标题均不变。OKF 导入页保留包内原 `concept_id`。
- 导出对带 `meta_snapshot.okf` 的自产页直接使用，不再走合成路径；无该元数据的历史页维持现有合成行为。

### 问答出图

- 检索仍是文本（关键词 / 向量 / generation index），不引入视觉模型、不喂像素。
- 进入上下文的知识页，附带其正文中的图片引用，以及通过 `PageEvidence` 关联资料的解析 md 中、落在命中片段窗口内的图片引用；以可展示 URL（现有 `wiki/media` 签发链路）形式放入上下文并告知模型可按需引用。未进入上下文的图不返回。
- 每条上下文附带图片数量有界；答案中的图片 Markdown 由前端现有媒体渲染链路展示。引用抽屉行为不变。

### 前端

- 设置页与新建弹窗按上述收敛；简介校验必填。
- 目录树对冻结根禁用删除 / 改名 / 拖出根的操作入口；「来源」目录不提供「新建页面」入口。
- 导入弹窗只剩 OKF 形态；预检摘要新增剥壳结果与导入层对齐预览（哪些文件夹并入哪个根、哪些新建）。
- 遵守 Web UI 硬约束：Tailwind `className`、语义 token、复用 AntD。

## Testing Decisions

- 好测试只断言对外行为：给定 ZIP 字节 → 预检返回的 `bundle_root`、目录对齐预览、页面表；执行后目录树形状、页面所在目录、`meta_snapshot`、index entry 与 Overview 内容；API 状态码与错误码。不绑定私有 helper 的调用次数。
- 结构冻结：bootstrap 出六根 + 待归类；删除 / 改名冻结根被拒；结构保存省略冻结根被拒；根上新建同级目录成功。prior art：`test_structure_service.py`、`test_directory_governance_contract.py`、`test_wiki_directory_views.py`。
- 简介：创建 / 更新缺简介返回 400；构建与 Overview 提示词包含 `introduction` 且不含 `purpose_md`；序列化器不再输出 `purpose_md` / `schema_md`。prior art：`test_wiki_kb_views.py`、`test_build.py`、`test_overview.py`。
- 存量迁移：老模板库迁移后含六根且原目录未动；`introduction` 为空时被回填。prior art：`test_directory_migrations.py`。
- 导入格式：缺省 / `markdown` 返回 400 `import_format_unsupported`；`okf` 正常。prior art：`test_okf_import.py`。
- 剥壳：`repo-main/` 单层、`test/llm_wiki/` 双层被剥；`IT/目录介绍.md` + `IT/wiki/` 在 `IT` 停止；唯一目录名为「实体」时停止；`assets` / `index.md` 不影响计数。以 `zipfile` 动态打包，不提交大文件。
- 对齐：`实体` 并入知识库「实体」且子层级保留；`测试` 在根上新建；整层无命中新建以导入层名命名的根；`entity` 不视为同名；包内「来源」文件夹成为普通目录；散页停止场景下 `wiki/实体` 不提升。重导入同一包页面数不变、全部 update。
- 导入后置链路回归：冲突 candidate、wikilink 关系、口语别名、图片落盘与 GC、`meta_snapshot.okf` 的既有测试全部保持通过；新增断言导入后语义 Overview 被触发且失败不阻断。prior art：`test_okf_import.py`、`test_generation_navigation.py`、`test_colloquial_alias.py`。
- 资料构建：生成页进对应知识根，不进「来源」；`meta_snapshot.okf` 含 `sources[{resource, material_id}]` 与稳定 `concept_id`；挪目录后 `concept_id` 不变；导出使用原生元数据。prior art：`test_material_unified_build.py`、`test_okf_export.py`。
- 问答出图：命中页正文含图时上下文带图 URL；关联资料解析 md 命中窗口内的图被带上、窗口外不带；无模型 fallback 路径不受影响。prior art：`test_wiki_context.py`、`test_retrieval.py`、`test_parsed_media.py`。
- 前端：设置页无用途页签、新建弹窗无模板选择、导入弹窗仅 OKF、冻结根无删除入口，用组件测试或 Storybook 锁住；不引入浏览器 E2E。
- 验证命令沿用 `DEVELOP.md`：server 用 sqlite `uv run pytest server/apps/opspilot/tests/wiki/ --no-cov`；web `pnpm lint`、`pnpm type-check`。

## Out of Scope

- 把运行时改成文件系统 OKF 仓库；DB Generation 仍是唯一真相。
- 视觉模型读图作答；HTML `<img>` 与附件链接的出图。
- 按 `concept_id` 而非标题匹配已有页面（元数据已就位，匹配规则另立变更）。
- OKF 导入登记为资料、OKF 重导入历史入口。
- 删除或迁移存量库中老模板产生的非冻结根目录。
- git URL / tarball 拉取；ZIP 内手动选择导入层。
- 目录级 Overview 路由算法调整、检索打分吃目录路径。
- 简介限长、多语言简介。

## Further Notes

- 本变更由一次 grill 会话收敛，17 个分叉的取舍已在实现决策中体现；其中「结构固定」最终定义为「六根冻结 + 根上可新增同级」，不是整树冻死。
- 与 llm_wiki 的对照：其 `raw/sources` 对应本变更的「来源」资料根；其 `wiki/sources` 摘要页在本变更中不再生成；其 `purpose.md` 只影响摄入提示词、不影响问答，与本变更简介的定位一致。
- 删除非 OKF 导入分支时，以「是否仅服务于 `markdown` / `third_party` / `native`」为唯一判据；与 OKF 共用的任何函数一律保留。
- 相关已实现 spec：`opspilot-wiki-okf-import`、`opspilot-wiki-okf-export`；本变更覆盖其中「只对齐第一层」「未命中进待归类」「只剥一层唯一顶目录」三条规则。
