# CMDB Custom Reporting Context

## 当前项目状态

- 当前分支已完成 **CMDB 自定义上报** 的主要后端实现，并已按“商业版功能”要求将核心实现下沉到 `server/apps/cmdb/enterprise/`。
- 社区层当前保留了最小兼容入口：
  - `server/apps/cmdb/models/__init__.py`
  - `server/apps/cmdb/urls.py`
  - `server/apps/cmdb/models/custom_reporting.py`
  - `server/apps/cmdb/serializers/custom_reporting.py`
  - `server/apps/cmdb/services/custom_reporting_*.py`
  - `server/apps/cmdb/views/custom_reporting.py`
- enterprise 缺省场景下，loader / shim / model registry 已做回退处理，避免：
  - 因缺少 `apps.cmdb.enterprise` 导致启动失败
  - `0024_custom_reporting` migration 与 Django app registry 不一致
- 当前 **不建议直接合并**。还剩 1 个真实阻断项：**identity 匹配缺少基于模型字段类型的稳定归一化**，可能导致某些幂等上报在数值/字符串混用时重复创建实例。

## 已实现功能

### 1. 自定义上报任务

- 支持任务新建、编辑、删除、列表、详情。
- 同组织下任务名唯一。
- 任务按组织/团队隔离，沿用现有权限模型。
- 任务创建时自动签发独立凭证。
- 支持凭证签发、轮换、作废、最近使用时间记录。

### 2. 双轨建模

- 支持绑定已有完整模型。
- 支持快速模型：
  - 创建时声明模型名、分类、身份键、清理策略相关配置
  - 首次上报自动登记字段
  - 新字段可持续追加

### 3. 数据上报与合并

- 支持实例数据上报。
- 支持关系上报：
  - 同批互引
  - 引用 CMDB 已存在实例
  - 引用尚未落地实例并转为 pending relation
- 底层复用现有 CMDB 合并/关系能力，不单独分叉图写入语义。

### 4. 清理与批次

- 支持批次记录落库。
- 支持待关联关系持久化与后续回补。
- 支持清理审核数据结构与任务详情聚合信息。
- 支持批次活动查询与最近批次概览。

### 5. 变更记录与接入文档

- 自定义上报变更写入 `custom_reporting_change` 场景。
- 支持任务级接入文档生成。
- change record 写失败已改为 **non-fatal**，避免“图数据已写入但批次被误标失败”。

### 6. Enterprise Overlay 调整

- 真实实现已迁移到：
  - `server/apps/cmdb/enterprise/models.py`
  - `server/apps/cmdb/enterprise/serializers.py`
  - `server/apps/cmdb/enterprise/views.py`
  - `server/apps/cmdb/enterprise/urls.py`
  - `server/apps/cmdb/enterprise/services/custom_reporting_*`
- custom-reporting 专属 model/merge helper 已从 community service 抽出至 enterprise helper。
- loader 仅在“enterprise 模块不存在”时回退，不再吞掉真实内部导入异常。

## 技术决策

### 1. 用户心智独立，底层引擎复用

- 自定义上报与自动发现保持产品层分离。
- 实际实例合并、关系写入、变更记录仍尽量复用 CMDB 现有能力，避免形成第二套语义。

### 2. Enterprise-only 采用 overlay，而不是直接写死在 community

- 用户要求这是商业版能力，因此核心实现放到 `server/apps/cmdb/enterprise/`。
- 社区层只保留最小入口和兼容壳。

### 3. Community fallback 需要兼顾 Django migration state

- `0024_custom_reporting.py` 仍位于 `cmdb` app migration 树。
- 因此当 enterprise 缺失时，community 层不能完全没有这些 model。
- 现采用 `server/apps/cmdb/models/custom_reporting.py` 提供 **同构 fallback model 定义**，保证 schema state 与 runtime registry 一致。

### 4. 关系重试必须幂等

- 已存在关系不会重复创建。
- 若同一关系再次上报但边属性变化，会更新已有边属性，而不是静默忽略。

### 5. 组织范围优先于 identity 命中

- 自定义上报 merge 时，已增加 `allowed_org_ids` 过滤，避免单命中场景误更新其他组织实例。
- 对“identity 非唯一”场景，已补充一层 scope-aware fallback，再按组织范围过滤后决定是否唯一。

### 6. Post-graph 非关键步骤不再反向污染批次状态

- change record 写入失败不再把已成功落图的批次标记为失败。
- 目前仍保留日志，便于后续补观测或补偿。

## 遗留问题

### 1. 阻断项：identity 类型归一化不稳定

- 当前 `query_entity_by_identity()` 按 Python 值类型选择 `int=` / `str=`。
- 但自定义上报入口对 identity 字段没有按模型属性类型做统一归一化。
- 风险：
  - 某 identity 字段在 CMDB 中是数值型
  - 一批上报 `123`
  - 另一批上报 `"123"`
  - 查询可能命不中已有实例，从而重复创建
- 该问题影响上报幂等性，是当前主要阻断项。

### 2. 快速模型 graph / SQL 双写仍非严格事务

- quick mode 下任务创建/更新时：
  - Django SQL 事务存在
  - 图模型 `create_model` / `update_model` / `create_model_attr` 不在同一事务域
- 若中途失败，理论上仍可能出现图侧已变更而 SQL 回滚的部分状态。
- 这是结构性一致性问题，尚未完成补偿式处理。

### 3. `last_reported_at` 与最终批次成功语义仍可进一步收紧

- 当前 `last_reported_at` 更新早于 `_persist_pending_relations()`。
- 若后续 pending relation 持久化失败，任务时间戳可能已刷新，但批次最终失败。
- 该问题不如 identity 归一化严重，但仍建议后续收口。

### 4. 前端商业版隔离尚未完成

- 目前这轮主要收敛的是 **server 侧 enterprise overlay**。
- web 侧 community 暴露路径、菜单、页面隔离未在本轮完全闭合。

## 下一步计划

### P0

1. 为 custom reporting identity lookup 增加 **按模型字段类型归一化**：
   - 在 merge 前或 query 前统一根据模型属性元数据做 coercion
   - 至少覆盖 int / str identity 场景
2. 增加对应回归覆盖：
   - `123` 与 `"123"` 命中同一实例
   - 非法类型输入的拒绝或规范化路径

### P1

1. 收敛 quick model create/update 的跨存储一致性：
   - 评估是否拆成“先图后 SQL + 失败补偿”
   - 或“先 SQL 标记，再异步/二阶段落图”
2. 调整 `last_reported_at` 更新时机：
   - 放到所有 required persistence 完成之后

### P2

1. 完成 web 侧 enterprise-only 隔离：
   - 菜单
   - API export
   - 页面入口
2. 完成一次 server + web 联合复核，再决定是否允许合并。

## 关键路径文件

- Enterprise 实现
  - `server/apps/cmdb/enterprise/models.py`
  - `server/apps/cmdb/enterprise/serializers.py`
  - `server/apps/cmdb/enterprise/views.py`
  - `server/apps/cmdb/enterprise/urls.py`
  - `server/apps/cmdb/enterprise/services/custom_reporting_task_service.py`
  - `server/apps/cmdb/enterprise/services/custom_reporting_ingest_service.py`
  - `server/apps/cmdb/enterprise/services/custom_reporting_document_service.py`
  - `server/apps/cmdb/enterprise/services/custom_reporting_model_service.py`
  - `server/apps/cmdb/enterprise/services/custom_reporting_merge_service.py`

- Community overlay / fallback
  - `server/apps/cmdb/models/__init__.py`
  - `server/apps/cmdb/urls.py`
  - `server/apps/cmdb/models/custom_reporting.py`

- 关键测试
  - `server/apps/cmdb/tests/test_models.py`
  - `server/apps/cmdb/tests/test_model_views.py`
  - `server/apps/cmdb/tests/test_misc_views.py`
  - `server/apps/cmdb/tests/test_serializers.py`
