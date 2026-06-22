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
