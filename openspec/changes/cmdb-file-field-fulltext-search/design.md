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
