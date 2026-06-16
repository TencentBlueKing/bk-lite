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
