# Cmdb File Field Fulltext Search

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/cmdb-file-field-fulltext-search/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

CMDB 全文检索通过遍历实例节点的全部属性做 `CONTAINS` 匹配，并排除一组「机器值」字段（ID / JSON）。被排除的字段类型（`organization` / `user` / `enum` / `tag` / `table`）都会生成一个可读的 `<field>_display` 冗余字段，全文检索改为命中这个冗余字段——所以它们「被排除但仍可搜索」。

最近新增的**附件（attachment）/ 图片（image）** 字段类型也被加入了全文检索排除列表（`display_field/cache.py:427`，通过 `is_file_attr_type`），但**没有为它们生成任何 `_display` 冗余字段**（`build_display_fields` 只处理上述 5 种类型）。结果是：文件字段「被排除且没有可搜索的冗余兜底」——文件的**文件名**（文件字段里唯一对用户有意义、可读的部分）在全文检索中**完全搜不到**，且无任何报错或提示，属于静默缺漏。

这是所有被排除类型中唯一一个「无 `_display` 兜底」的类型，与既有冗余机制不对称。本变更补齐该冗余，使附件/图片可按**文件名（去扩展名、去路径）** 被全文检索命中。

## What Changes

- 新增 `DisplayFieldConverter.convert_file(value)`：把文件字段的元数据 JSON 数组转换为「逗号分隔的文件名词干（stem）」字符串，用于全文检索冗余。**只保留文件名主体**——去掉目录路径、去掉最后一个扩展名。
- 扩展 `DisplayFieldHandler.build_display_fields`：在遍历模型字段时，对 `is_file_attr_type(attr_type)` 为真的字段额外生成 `<attr_id>_display` 冗余字段（与 `table` 等类型同一套机制）。社区缺企业版时 `is_file_attr_type` 恒 False → 该分支 inert，社区行为不变。
- 不改动三个全文检索查询（`full_text` / `full_text_stats` / `full_text_by_model`）：它们已遍历 `keys(n)` 并排除原始 attr_id；`<attr_id>_display` 不在排除列表中，会被自动检索；`remove_display_fields` 在读路径自动剥离，输出不受影响。
- 全类型审计后补充：新增 `SENSITIVE_FIELD_TYPES = {"pwd"}`，把密码类型也排除出全文检索（密文，无 `_display`，刻意不可搜索）。其余类型经核对均已正确：str/int/bool/time 原值直接可搜；enum/user/organization/tag/table 经 `_display` 可搜；attachment/image 本次补齐。

## Capabilities

### New Capabilities

- `cmdb-file-field-fulltext-search`: 附件/图片字段生成「文件名词干」冗余字段，使其文件名可被 CMDB 全文检索命中；原始元数据 JSON（URL/ID/大小）仍排除在索引外。

### Modified Capabilities

<!-- 无既有 spec 描述 CMDB 全文检索冗余行为；本变更为新增能力。 -->

## Impact

- **server/apps/cmdb/display_field/handler.py**：新增 `convert_file`；`build_display_fields` 增加文件类型分支（consult `is_file_attr_type`）。
- **server/apps/cmdb/display_field/cache.py**：无需改动（排除列表已含文件 attr_id；`_display` 本就不在排除列表）。
- **server/apps/cmdb/graph/falkordb.py**：无需改动（三个全文检索方法自动覆盖 `_display`）。
- **企业版 overlay（apps/cmdb_enterprise）**：仅需注册 `attachment`/`image` 到 `file_attr_types()`（已存在）；`normalize_file_fields` 产出的元数据 JSON 形状即 `convert_file` 的输入，无需改动。
- **行为变化**：搜索 `report` 可命中附件名为 `report.pdf` 的实例；搜索 `pdf` 或完整 `report.pdf` **不**命中（按产品决策：只索引去扩展名的文件名主体）。
- **数据迁移**：存量实例的文件字段在**下次保存前**没有 `_display`，仍搜不到；需要回填的话单独评估（见 design 的 Open Questions）。

## Implementation Decisions

## Context

全文检索（`graph/falkordb.py` 的 `full_text` / `full_text_stats` / `full_text_by_model`）对每个实例节点：遍历 `keys(n)` → 跳过 `ExcludeFieldsCache.get_exclude_fields()` 中的字段 → 对其余字段做 `toLower(toString(n[key])) CONTAINS toLower(search)`。

冗余机制（`display_field/`）：写实例时 `build_display_fields` 为「机器值」类型生成 `<attr_id>_display` 可读冗余；读实例时 `remove_display_fields` 剥离。排除列表 = 模型里这些类型的**原始 attr_id**（不含 `_display`），所以 `_display` 始终被检索。

不对称点：`cache.py:_build_exclude_fields` 用 `attr_type in EXCLUDE_FIELD_TYPES or is_file_attr_type(attr_type)` 把文件字段也排除了，但 `handler.py:build_display_fields` 只认 `DISPLAY_FIELD_TYPES`（不含文件类型），所以文件字段被排除却无冗余 → 文件名搜不到。

## Goals / Non-Goals

**Goals**
- 附件/图片字段的**文件名主体**（去路径、去扩展名）可被全文检索命中。
- 复用既有冗余机制（与 `table` 同构），不新增查询路径、不改三个 `full_text*` 方法。
- 社区无企业版时零行为变化。

**Non-Goals**
- 不索引文件扩展名、目录路径、URL、文件 ID、大小。
- 不索引文件**内容**（不做 OCR / 文档解析）。
- 不在本变更里回填存量数据（见 Open Questions）。
- 不改前端搜索 UI。

## Decisions

### D1：文件名规范化 = basename + 去最后一个扩展名

`convert_file` 对每个文件项的 `name` 取词干：
```
base = os.path.basename(name.replace("\\", "/"))   # 去路径，兼容 Windows 分隔符
stem, _ext = os.path.splitext(base)                # 去最后一个扩展名
```
- `reports/2026 Q2 报表.pdf` → `2026 Q2 报表`
- `logo.png` → `logo`
- `archive.tar.gz` → `archive.tar`（只去最后一个扩展名——产品选择「不索引扩展名」，`.tar` 作为名字主体保留；如需去全部复合扩展名再议）
- `noext` → `noext`；`.gitignore` → `.gitignore`（splitext 视其为无扩展名）
- 多文件 → 用 `DISPLAY_VALUES_SEPARATOR`（`", "`）连接，与其他 `_display` 一致。

**为何去扩展名**：按产品决策只让用户按「文件名」搜，扩展名（pdf/png）是噪声，会让所有 PDF 互相污染搜索结果。**代价**：搜 `report.pdf` 全名时不命中（`CONTAINS` 在 `"report"` 里找不到 `"report.pdf"`）——这是有意取舍，需在用户文档/提示里说明。

### D2：在社区 `build_display_fields` 里 consult `is_file_attr_type`，而非放进企业 `normalize_file_fields`

两个候选：
- **(A) 社区 handler 分支**（选中）：`build_display_fields` 增加 `elif is_file_attr_type(attr_type): convert_file(...)`。冗余生成逻辑集中在社区、可在本仓直接 TDD；与排除路径 `cache.py` 同样 consult `is_file_attr_type`，两端对称、单一真相源。
- (B) 企业 `normalize_file_fields` 内产出 `_display`：逻辑落在不在本仓的 overlay，无法在此 TDD，且把「冗余生成」拆散到两处。

选 A。`convert_file` 是纯函数（社区），企业 overlay 无需任何改动——它产出的元数据 JSON 形状就是 `convert_file` 的输入。

### D3：输入形状兼容 str(JSON) 与 list

`normalize_file_fields` 把值规范化为元数据 JSON 数组，但落库/回读可能是 JSON 字符串。`convert_file` 同 `convert_table` 一样两种都接：`isinstance(str)` 先 `json.loads`，失败则原样返回字符串；`list` 直接用；其他类型返回 `str(value)`。每项取 `dict.get("name")`，缺失/空跳过。

### D4：异常降级不污染索引

`build_display_fields` 既有 try/except 降级为 `str(original_value)`。但文件字段降级成原始 JSON 会把 URL/ID 灌进可搜索索引，违背 Non-Goal。**决策**：`convert_file` 自身吞掉解析异常返回 `""`，不依赖外层 `str()` 降级；外层 except 对文件类型也应降级为 `""` 而非 `str(original_value)`。

## Risks / Trade-offs

- **存量数据不可搜**：仅新写入/更新的实例才有 `_display`。可接受；如需全量，提供一次性管理命令重算（Open Question）。
- **全名搜索失效**：D1 的代价，已知并接受。
- **同名词干污染**：`a/report.pdf` 与 `b/report.docx` 都索引为 `report` → 搜 `report` 都命中。符合「按文件名搜」预期。
- **性能**：`_display` 在写时计算、随节点存储，全文检索只是多遍历一个字符串键；可忽略。

### D5：存量回填走「模型字段变更」钩子（沿用 enum 的 `update_enum_instances_display` 范式）

已存在的对称范式：`update_enum_instances_display(model_id, attr_id, options)` 在枚举选项变更时遍历该模型全部实例、重算 `_display` 写回（`views/model.py` 调用）。
新增 `ModelManage.rebuild_file_instances_display(model_id, attr_id)`：同样遍历实例，对含文件值的实例用 `convert_file` 重算 `<attr_id>_display` 写回。在 `model_attr_update` 视图里 `elif is_file_attr_type(attr_type)` 触发。

- **为何「重算」而非「仅缺失时补」**：文件名词干由实例自身数据决定、不依赖模型配置，重算即幂等，等价于「缺失补全」，且与 enum 路径一致，避免两套语义。
- **与 enum 的本质差别**：enum 因「选项改名→显示值过期」必须重算；文件无此过期场景，钩子的唯一价值是**回填历史实例**（功能上线前已有文件值但无 `_display`）。
- **触发面**：文件字段建后禁类型互切，故 `_handle_attr_type_change` 对文件恒不触发；回填只发生在 `update_model_attr`（编辑文件字段）。新建文件字段时存量实例无该字段值 → 无需回填。

## Open Questions

- 是否再加一次性管理命令 `rebuild_file_display`（遍历所有含文件字段的模型批量回填），用于上线即时全量？当前靠「编辑模型字段」逐模型自愈；若需即时全量再补。
- `archive.tar.gz` 这类复合扩展名是否要去到 `archive`？当前只去最后一段，保留 `archive.tar`。待产品确认。
- 大模型实例量大时，回填遍历应否转 Celery 异步？现沿用 enum 同步遍历；超大模型需评估。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-06-16
```

## Capability Deltas

### cmdb-file-field-fulltext-search

## ADDED Requirements

### Requirement: 附件/图片字段生成文件名词干冗余字段

写入或更新实例时，对于属于文件型（attachment/image，由 `is_file_attr_type` 判定）的字段，系统 SHALL 生成 `<attr_id>_display` 冗余字段，其值为该字段所有文件「文件名词干」的逗号分隔字符串。文件名词干 = 文件 `name` 去掉目录路径、去掉最后一个扩展名。

#### Scenario: 单个附件生成文件名词干
- **WHEN** 某 attachment 字段 `doc` 的值为 `[{"name": "report.pdf", "url": "...", "id": 1, "size": 1024}]`
- **THEN** 实例数据 SHALL 含 `doc_display = "report"`
- **AND** `doc_display` SHALL NOT 包含扩展名 `.pdf`、URL、ID 或大小

#### Scenario: 多个文件以分隔符连接
- **WHEN** 某 image 字段的值为 `[{"name": "logo.png"}, {"name": "banner.jpg"}]`
- **THEN** 对应 `_display` SHALL 为 `"logo, banner"`

#### Scenario: 文件名含目录路径时只取 basename
- **WHEN** 文件 `name` 为 `"reports/2026/年度报表.xlsx"`
- **THEN** 词干 SHALL 为 `"年度报表"`（去路径、去扩展名）

#### Scenario: 复合扩展名只去最后一段
- **WHEN** 文件 `name` 为 `"archive.tar.gz"`
- **THEN** 词干 SHALL 为 `"archive.tar"`

#### Scenario: 无扩展名文件名原样保留
- **WHEN** 文件 `name` 为 `"README"`
- **THEN** 词干 SHALL 为 `"README"`

#### Scenario: 空值或空列表产出空字符串
- **WHEN** 文件字段值为 `None`、`""` 或 `[]`
- **THEN** 对应 `_display` SHALL 为 `""`

#### Scenario: 输入为 JSON 字符串时同样解析
- **WHEN** 文件字段值为 JSON 字符串 `'[{"name": "x.pdf"}]'`
- **THEN** 对应 `_display` SHALL 为 `"x"`

#### Scenario: 解析失败时降级为空字符串而非原始 JSON
- **WHEN** 文件字段值是无法解析为文件数组的内容
- **THEN** 对应 `_display` SHALL 为 `""`
- **AND** SHALL NOT 把原始 JSON/URL/ID 写入 `_display`（避免污染全文索引）

### Requirement: 文件名词干可被全文检索命中

全文检索（`full_text` / `full_text_stats` / `full_text_by_model`）SHALL 能通过文件名词干匹配到含该附件/图片的实例；原始文件字段（元数据 JSON）SHALL 仍排除在检索之外。

#### Scenario: 按文件名主体搜到实例
- **GIVEN** 某实例的 attachment 字段含文件 `report.pdf`，已生成 `doc_display = "report"`
- **WHEN** 用户全文检索 `report`
- **THEN** 该实例 SHALL 出现在结果中

#### Scenario: 原始元数据不可被检索命中
- **GIVEN** 某实例文件的 URL 中含字符串 `minio`
- **WHEN** 用户全文检索 `minio`
- **THEN** 该实例 SHALL NOT 因文件 URL 而被命中（原始文件字段仍在排除列表中）

#### Scenario: 扩展名不参与匹配
- **GIVEN** 某实例 attachment 含文件 `report.pdf`，`doc_display = "report"`
- **WHEN** 用户全文检索 `pdf`
- **THEN** 该实例 SHALL NOT 仅因该文件被命中

#### Scenario: 社区无企业版时行为不变
- **GIVEN** 部署未注册企业版文件类型（`is_file_attr_type` 恒 False）
- **WHEN** 写入任意实例
- **THEN** SHALL NOT 为任何字段生成文件类 `_display`
- **AND** 全文检索行为 SHALL 与变更前一致

### Requirement: 模型字段变更时回填历史实例的文件名词干冗余

修改文件型（attachment/image）模型字段时，系统 SHALL 遍历该模型的实例，对含文件值的实例重算并写回 `<attr_id>_display`，使功能上线前已有的存量文件也可被全文检索命中。

#### Scenario: 历史实例缺失 _display 时被回填
- **GIVEN** 某实例的 attachment 字段 `doc` 值为 `[{"name": "report.pdf"}]` 但无 `doc_display`
- **WHEN** 在模型管理中更新字段 `doc`
- **THEN** 该实例 SHALL 被写入 `doc_display = "report"`

#### Scenario: 无文件值的实例不写入
- **WHEN** 回填遍历到不含该文件字段值的实例
- **THEN** SHALL NOT 为其写入 `_display`

#### Scenario: 重算幂等
- **GIVEN** 某实例已有正确的 `doc_display`
- **WHEN** 再次触发回填
- **THEN** 写回值 SHALL 与原值一致（文件名词干仅由实例文件数据决定）

### Requirement: 全字段类型排除完整性不变量

被全文检索排除的字段类型集合 SHALL 等于「展示型 ∪ 文件型 ∪ 敏感型」，且其中展示型与文件型 SHALL 各有 `_display` 冗余生成器，敏感型 SHALL 无 `_display`（刻意不可搜索）。可读原值类型（str/int/bool/time）SHALL NOT 被排除。

#### Scenario: 每个展示型/文件型被排除类型都有 _display 生成器
- **WHEN** 遍历 `DISPLAY_FIELD_TYPES ∪ file_attr_types()` 中每个类型
- **THEN** `build_display_fields` SHALL 为其产出 `<attr>_display`

#### Scenario: 密码类型排除且无可搜索冗余
- **GIVEN** 模型含 pwd 类型字段 `secret`
- **WHEN** 构建排除字段列表
- **THEN** `secret` SHALL 在排除列表中
- **AND** `secret_display` SHALL NOT 存在（密文不可被全文检索命中）

#### Scenario: 可读原值类型不被排除
- **WHEN** 模型含 str/int/bool/time 字段
- **THEN** 这些字段 SHALL NOT 被排除（原值直接可搜）

## Work Checklist

遵循 TDD：先写失败测试再实现。测试约定见 `server/docs/testing-guide.md`。
环境说明：本 worktree 装有 `cmdb_enterprise`，`is_file_attr_type('attachment'/'image')` 为真；
带 `@pytest.mark.django_db` 的用例会连远端 10.10.41.149 Postgres（超时），故新用例尽量不依赖 DB。

## 1. `convert_file` 纯函数（文件名词干） ✅

- [x] 1.1 失败用例覆盖：单文件去扩展名、多文件分隔、去路径(basename)、Windows 路径、复合扩展名只去最后一段、无扩展名保留、空值/空列表→""、JSON 字符串输入、解析失败→""、无 name 项跳过。（`tests/test_display_field.py`）
- [x] 1.2 实现 `DisplayFieldConverter.convert_file`（`display_field/handler.py`）。
- [x] 1.3 全绿。

## 2. `build_display_fields` 识别文件类型 ✅

- [x] 2.1 失败用例：注册假企业扩展 → attachment/image 字段产出正确 `_display`；解析失败 `_display=""` 而非原始 JSON；社区(摘除 model_ops 槽位)不产出。
- [x] 2.2 实现：`build_display_fields` 增加 `is_file_attr_type` 分支 + 文件型 except 降级 `""`。
- [x] 2.3 社区无企业版回归用例（显式 pop `model_ops`）。
- [x] 2.4 全绿。

## 3. 排除链路确认 ✅

- [x] 3.1 `ExcludeFieldsCache._build_exclude_fields` 测试：原始文件字段 `doc` 被排除、`status` 被排除、`inst_name` 不排除、`doc_display`/`status_display` **不**排除（确保冗余可搜索）。
- [x] 3.2 `remove_display_fields` 剥离 `*_display`（既有用例覆盖）。
- [~] 3.3 全文检索三个 `full_text*` 方法无需改动：已遍历 `keys(n)` 并排除原始 attr_id，`_display` 自动纳入检索（设计确认，无代码改动）。

## 4. 存量回填（模型字段变更钩子） ✅

- [x] 4.1 失败用例：`rebuild_file_instances_display` 回填含文件值实例的文件名词干、无文件值实例不写、空实例集返回 0。（`tests/test_model_service_methods.py`，fake_graph，无 DB）
- [x] 4.2 实现 `ModelManage.rebuild_file_instances_display`（`services/model.py`，沿用 enum 范式）。
- [x] 4.3 视图 `model_attr_update` 增加 `elif is_file_attr_type(attr_type)` 触发回填（`views/model.py` + import）。
- [x] 4.4 视图用例 `test_model_attr_update_file_triggers_rebuild`（`tests/test_model_views.py`，django_db → 仅 CI 执行；本地远端 DB 不可达）。
- [x] 4.5 视图模块 import 冒烟校验（无循环导入/拼写错）。

## 5. 收尾

- [x] 5.1 触达的离线用例全绿（33 passed）：convert_file/build_display/exclude/rebuild_file/remove_display。
- [ ] 5.2 在有测试 DB 的 CI 上跑全量 `cd server && make test`，确认 django_db 用例（含 enum/org/user 转换、view 测试）无回归。
- [ ] 5.3 真机/集成验证：建含附件字段的模型→上传 `report.pdf`→全文检索 `report` 命中、`pdf`/URL 片段不命中。
- [ ] 5.4 （可选）一次性管理命令 `rebuild_file_display` 全量回填——按 design Open Question 决策。
- [x] 5.5 更新记忆 `cmdb-file-field-feature-state`：补「文件字段已支持按文件名词干全文检索 + 回填钩子」；并纠正「cmdb_enterprise 在本 worktree 实为已安装」。
