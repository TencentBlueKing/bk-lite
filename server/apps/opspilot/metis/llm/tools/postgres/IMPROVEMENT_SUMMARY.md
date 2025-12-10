# PostgreSQL 动态查询工具改进总结

## 改进日期
2025-12-10

## 问题分析

### 用户反馈的问题
> "执行效果不理想,我觉得工具有缺失,提示词做的不够好导致的"

### 原问题
用户询问: "知识库有多少个,每个知识库有多少个分块,给我个表看看"

### AI执行出现的错误

1. **概念混淆**: 
   - AI混淆了"知识库表"(数据库表)和"知识库记录"(业务实体)
   - 错误地将包含"knowledge"关键词的所有表都视为知识库

2. **缺少层级理解**:
   - 没有识别出知识库→文档→分块的三层关系
   - 没有利用外键信息理解表之间的父子关系

3. **统计方法错误**:
   - 使用简单的表行数统计,而不是聚合查询
   - 没有通过JOIN和GROUP BY进行正确的层级统计

4. **工具使用不当**:
   - `get_sample_data` 只能获取单表数据,无法统计关联关系
   - 缺少对聚合查询的理解和使用

## 改进方案

### 1. 增强工具提示词 (Prompt Engineering)

#### 1.1 `get_table_schema_details` 工具改进

**改进前**:
```python
"""
获取表的详细结构信息,用于构建动态查询

**何时使用此工具:**
- 需要了解表的完整列信息以构建SELECT查询
- 需要知道字段类型以构建WHERE条件
- 需要了解索引以优化查询
- 需要知道约束以理解数据关系
```

**改进后**:
```python
"""
获取表的详细结构信息,用于构建动态查询和理解数据关系

**何时使用此工具:**
- 需要了解表的完整列信息以构建SELECT查询和JOIN条件
- 需要通过外键理解表之间的关系和层级结构
- 分析业务实体之间的关联关系(如:知识库→文档→分块)
- ...

**业务理解提示:**
- 外键字段(如xxx_id)通常指向父表,用于关联查询
- 主键通常是业务实体的唯一标识
- 表名模式(如prefix_entityname)可能表示业务模块
- 相同前缀的表可能属于同一业务域
```

**关键改进点**:
- ✅ 强调外键的作用和JOIN用途
- ✅ 提示AI理解表之间的层级关系
- ✅ 增加业务理解指导

#### 1.2 `search_tables_by_keyword` 工具改进

**改进前**:
```python
"""
根据关键字搜索相关的表和列,帮助找到需要查询的表

**何时使用此工具:**
- 不确定数据存储在哪个表中
- 根据业务关键词查找相关表
- 查找包含特定列名的表
```

**改进后**:
```python
"""
根据关键字搜索相关的表和列,帮助发现业务实体及其数据存储位置

**何时使用此工具:**
- 不确定业务数据存储在哪个表中(如:知识库、用户、订单)
- 根据业务关键词查找相关表(如:knowledge→知识库相关表)
- 探索业务模块的表结构(如:搜索"payment"找支付相关表)
- ...

**搜索策略提示:**
- 使用业务术语搜索(如:知识库→knowledge)
- 使用实体关系词搜索(如:文档→document)
- 使用关联词搜索(如:chunk→分块)
- 结果会标注匹配类型(表名匹配/列名匹配)
```

**关键改进点**:
- ✅ 强调业务实体发现
- ✅ 提供搜索策略指导
- ✅ 解释搜索结果的含义

#### 1.3 `execute_safe_select` 工具改进

**改进前**:
```python
"""
执行安全的SELECT查询

**何时使用此工具:**
- 执行动态生成的SELECT查询
- 根据schema信息构建并执行查询
- 验证查询结果

**工具能力:**
- 执行复杂的SELECT查询(支持JOIN、子查询、CTE等)
- 自动限制返回行数
```

**改进后**:
```python
"""
执行安全的SELECT查询,支持聚合统计、多表关联等复杂查询

**何时使用此工具:**
- 执行动态生成的SELECT查询
- 统计聚合数据(COUNT, SUM, AVG等)
- 多表关联查询(JOIN, 子查询)
- ...

**SQL编写规范:**

✅ **聚合统计示例:**
SELECT kb.id, kb.name, COUNT(d.id) as doc_count
FROM knowledge_base kb
LEFT JOIN document d ON d.knowledge_base_id = kb.id
GROUP BY kb.id, kb.name

✅ **多层关联示例:**
SELECT 
    kb.id as kb_id,
    kb.name as kb_name,
    COUNT(DISTINCT d.id) as doc_count,
    COUNT(c.id) as chunk_count
FROM knowledge_base kb
LEFT JOIN document d ON d.kb_id = kb.id
LEFT JOIN chunk c ON c.document_id = d.id
GROUP BY kb.id, kb.name

**业务查询思路提示:**
- 需要统计数量时,使用 COUNT() 函数
- 需要分组统计时,使用 GROUP BY
- 需要关联数据时,根据外键字段使用 JOIN
- 父子关系通常是 parent.id = child.parent_id
```

**关键改进点**:
- ✅ 增加聚合查询示例
- ✅ 提供多层JOIN示例
- ✅ 添加业务查询思路指导
- ✅ 解释GROUP BY和JOIN的使用场景

### 2. 创建业务查询指南文档

新增文件: `BUSINESS_QUERY_GUIDE.md`

**核心内容**:
1. **理解数据层级关系**: 如何识别父子关系
2. **发现层级关系的方法**: 3步骤工作流
3. **构建统计查询**: 3个典型场景的SQL模式
4. **常见业务场景**: 知识库分析、用户活跃度、时间维度统计
5. **工具使用流程**: 5步标准分析流程
6. **常见错误和解决方案**: 重复计数、缺少GROUP BY、JOIN类型错误

**价值**:
- 📚 为AI提供系统化的业务查询知识库
- 🎯 提供可复用的SQL模式和最佳实践
- 🛠️ 提供排错指南和解决方案

### 3. 改进效果对比

#### 改进前的执行流程

```
用户: "知识库有多少个,每个知识库有多少个分块"
  ↓
AI: search_tables_by_keyword(keyword="knowledge")
  ↓ 找到13个包含knowledge的表
AI: get_sample_data(table="opspilot_knowledgegraph", columns="knowledge_base_id")
  ↓ 获取2条记录
AI: "共识别出5个知识库表,每个表的分块数量..." ❌ 错误理解
```

**问题**:
- ❌ 混淆了"表"和"记录"
- ❌ 使用表行数作为分块数量
- ❌ 没有理解层级关系
- ❌ 没有使用聚合查询

#### 改进后的预期流程

```
用户: "知识库有多少个,每个知识库有多少个分块"
  ↓
AI: search_tables_by_keyword(keyword="knowledge")
  ↓ 找到knowledge_mgmt_knowledgebase, knowledge_mgmt_knowledgedocument等表
AI: get_table_schema_details(table="knowledge_mgmt_knowledgebase")
  ↓ 分析表结构,发现主键id
AI: get_table_schema_details(table="knowledge_mgmt_knowledgedocument")
  ↓ 发现外键knowledge_base_id → knowledge_mgmt_knowledgebase.id
AI: search_tables_by_keyword(keyword="chunk")
  ↓ 找到分块表(假设为chunk表)
AI: get_table_schema_details(table="chunk_table")
  ↓ 发现外键document_id → knowledge_mgmt_knowledgedocument.id
AI: 理解层级关系: knowledge_base → document → chunk
  ↓
AI: execute_safe_select(sql="""
    SELECT 
        kb.id as knowledge_base_id,
        kb.name as knowledge_base_name,
        COUNT(DISTINCT d.id) as document_count,
        COUNT(c.id) as chunk_count
    FROM knowledge_mgmt_knowledgebase kb
    LEFT JOIN knowledge_mgmt_knowledgedocument d 
        ON d.knowledge_base_id = kb.id
    LEFT JOIN chunk_table c 
        ON c.document_id = d.id
    GROUP BY kb.id, kb.name
    """)
  ↓
AI: 格式化为表格输出 ✅ 正确结果
```

**改进点**:
- ✅ 正确识别业务实体(知识库记录,不是表)
- ✅ 通过外键理解层级关系
- ✅ 使用聚合查询统计数量
- ✅ 使用多表JOIN关联数据

## 技术细节

### 外键关系识别

工具返回的外键信息格式:
```json
{
  "foreign_keys": [
    {
      "constraint_name": "fk_document_kb",
      "columns": ["knowledge_base_id"],
      "foreign_schema": "public",
      "foreign_table": "knowledge_mgmt_knowledgebase",
      "foreign_columns": ["id"]
    }
  ]
}
```

**AI应该理解**:
- `columns`: 当前表的外键字段
- `foreign_table`: 父表名称
- `foreign_columns`: 父表的主键字段
- 关联关系: `current_table.knowledge_base_id = foreign_table.id`

### 聚合查询模式

#### 模式1: 一对多统计
```sql
SELECT 
    parent.id,
    parent.name,
    COUNT(child.id) as child_count
FROM parent_table parent
LEFT JOIN child_table child ON child.parent_id = parent.id
GROUP BY parent.id, parent.name
```

#### 模式2: 多层级统计
```sql
SELECT 
    L1.id,
    L1.name,
    COUNT(DISTINCT L2.id) as L2_count,
    COUNT(L3.id) as L3_count
FROM level1 L1
LEFT JOIN level2 L2 ON L2.L1_id = L1.id
LEFT JOIN level3 L3 ON L3.L2_id = L2.id
GROUP BY L1.id, L1.name
```

**关键技术点**:
- `LEFT JOIN`: 保留所有父记录,即使没有子记录
- `COUNT(DISTINCT ...)`: 避免多层JOIN导致的重复计数
- `GROUP BY`: 必须包含所有非聚合列

## 改进成果验证

### 验证方法
1. ✅ 工具注册测试: `uv run ./manage.py parse_tools_yml`
   - 结果: 44个postgres工具正常注册
2. ✅ 文档完整性检查: 
   - `dynamic.py`: 工具函数文档字符串已增强
   - `BUSINESS_QUERY_GUIDE.md`: 业务查询指南已创建
3. ⏳ 实际场景测试: 需要在真实环境中验证AI是否能正确理解和执行

### 预期效果

**改进前**:
- AI容易混淆表和记录的概念
- 不理解如何进行层级数据统计
- 缺少聚合查询的知识

**改进后**:
- AI能理解数据层级关系(通过外键分析)
- AI能构建正确的聚合统计SQL
- AI能使用多表JOIN进行关联查询
- AI有系统化的业务查询知识库参考

## 后续优化建议

### 1. 创建示例案例库
为常见业务场景创建SQL模板,如:
- 用户-订单-商品统计
- 项目-任务-子任务统计
- 组织-部门-员工统计

### 2. 增加自动化表关系发现工具
开发专门的工具自动分析表之间的关系:
```python
@tool()
def analyze_table_relationships(
    root_table: str,
    max_depth: int = 3
):
    """
    自动分析以某个表为根的关系树
    
    Returns:
        - 父子关系图
        - JOIN路径建议
        - 统计SQL模板
    """
```

### 3. 增加查询验证工具
在执行聚合查询前,先验证SQL的正确性:
```python
@tool()
def validate_aggregation_query(sql: str):
    """
    验证聚合查询的正确性
    
    检查:
    - GROUP BY包含所有非聚合列
    - 多表JOIN时是否需要DISTINCT
    - 是否正确使用LEFT/INNER JOIN
    """
```

### 4. 性能优化建议
对于大数据量的聚合查询,提供性能优化建议:
- 索引利用分析
- 查询计划优化
- 数据采样统计(对于非常大的表)

## 总结

本次改进主要通过**增强提示词工程**和**创建知识库文档**的方式,提升AI对业务层级数据统计的理解能力:

1. **问题根源**: 工具提示词缺少业务理解指导,AI缺乏聚合查询知识
2. **解决方案**: 
   - 增强3个核心工具的文档字符串
   - 创建系统化的业务查询指南
   - 提供SQL模式和最佳实践
3. **预期效果**: AI能正确理解层级关系并构建聚合统计查询
4. **验证状态**: 工具注册成功,等待实际场景验证

**改进类型**: 非破坏性增强 (只增加文档,不修改工具逻辑)
**向后兼容**: 完全兼容现有代码
**风险评估**: 低风险 (仅文档和提示词变更)
