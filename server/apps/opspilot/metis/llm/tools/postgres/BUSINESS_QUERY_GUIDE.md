# PostgreSQL 业务查询指南

## 概述
本指南帮助AI理解如何使用动态SQL工具进行业务数据分析,特别是层级关系数据的统计。

## 核心原则

### 1. 理解数据层级关系
在关系数据库中,业务实体通常存在父子层级关系:
- **父实体**: 通常有主键 `id`
- **子实体**: 通常有外键 `parent_id` 或 `parent_table_id`
- **关系类型**: 一对多 (1:N)

**示例:**
```
知识库 (knowledge_base)
  └── 文档 (document) [外键: knowledge_base_id]
       └── 分块 (chunk) [外键: document_id]
```

### 2. 发现层级关系的方法

#### 步骤1: 搜索相关表
使用 `search_tables_by_keyword` 搜索业务关键词:
```python
search_tables_by_keyword(keyword="knowledge")
```

#### 步骤2: 分析表结构
使用 `get_table_schema_details` 查看表结构,重点关注:
- **主键**: 通常是 `id`
- **外键**: `foreign_keys` 数组,包含关联的父表信息
- **外键字段命名**: 通常是 `parent_table_id` 或 `parent_table_name_id`

#### 步骤3: 绘制关系图
根据外键关系绘制实体关系:
```
Table A (id) ← Table B (table_a_id) ← Table C (table_b_id)
```

### 3. 构建统计查询

#### 场景1: 统计每个父实体的子实体数量

**需求**: 统计每个知识库有多少个文档

**思路**:
1. 主表: `knowledge_base` (父)
2. 从表: `document` (子)
3. 关联字段: `document.knowledge_base_id = knowledge_base.id`
4. 统计方法: `COUNT(document.id)`

**SQL示例**:
```sql
SELECT 
    kb.id,
    kb.name,
    COUNT(d.id) as document_count
FROM knowledge_base kb
LEFT JOIN document d ON d.knowledge_base_id = kb.id
GROUP BY kb.id, kb.name
```

**关键点**:
- 使用 `LEFT JOIN` 确保即使没有子记录也显示父记录
- 使用 `GROUP BY` 按父实体分组
- 使用 `COUNT()` 统计子实体数量

#### 场景2: 多层级统计

**需求**: 统计每个知识库的文档数和分块数

**思路**:
1. 主表: `knowledge_base` (层级1)
2. 第二层: `document` (层级2)
3. 第三层: `chunk` (层级3)
4. 关联链: `kb.id → d.kb_id → c.doc_id`

**SQL示例**:
```sql
SELECT 
    kb.id as knowledge_base_id,
    kb.name as knowledge_base_name,
    COUNT(DISTINCT d.id) as document_count,
    COUNT(c.id) as chunk_count
FROM knowledge_base kb
LEFT JOIN document d ON d.knowledge_base_id = kb.id
LEFT JOIN chunk c ON c.document_id = d.id
GROUP BY kb.id, kb.name
ORDER BY kb.id
```

**关键点**:
- 使用 `COUNT(DISTINCT d.id)` 避免重复计数
- 多次 `LEFT JOIN` 连接多层表
- 在 `GROUP BY` 中包含所有非聚合列

#### 场景3: 条件过滤统计

**需求**: 只统计已启用的知识库

**SQL示例**:
```sql
SELECT 
    kb.id,
    kb.name,
    COUNT(d.id) as document_count
FROM knowledge_base kb
LEFT JOIN document d ON d.knowledge_base_id = kb.id
WHERE kb.status = 'active'  -- 过滤条件
GROUP BY kb.id, kb.name
```

## 常见业务场景

### 场景A: 知识库分析

**问题**: "知识库有多少个,每个知识库有多少个分块?"

**分析步骤**:
1. 搜索相关表: `search_tables_by_keyword(keyword="knowledge")`
2. 识别核心表: `knowledge_mgmt_knowledgebase` (知识库主表)
3. 查看表结构: `get_table_schema_details(table_name="knowledge_mgmt_knowledgebase")`
4. 寻找分块表: 搜索 "chunk" 或 "document"
5. 分析外键关系: 找到 `document.knowledge_base_id → knowledge_base.id`
6. 构建统计SQL:
   ```sql
   SELECT 
       kb.id,
       kb.name,
       COUNT(DISTINCT doc.id) as document_count,
       COUNT(chunk.id) as chunk_count
   FROM knowledge_mgmt_knowledgebase kb
   LEFT JOIN knowledge_mgmt_knowledgedocument doc 
       ON doc.knowledge_base_id = kb.id
   LEFT JOIN <chunk_table> chunk 
       ON chunk.document_id = doc.id
   GROUP BY kb.id, kb.name
   ```

### 场景B: 用户活跃度统计

**问题**: "每个用户创建了多少个项目?"

**SQL模式**:
```sql
SELECT 
    u.id,
    u.username,
    COUNT(p.id) as project_count
FROM users u
LEFT JOIN projects p ON p.user_id = u.id
GROUP BY u.id, u.username
```

### 场景C: 时间维度统计

**问题**: "过去7天每天创建了多少个订单?"

**SQL模式**:
```sql
SELECT 
    DATE(created_at) as order_date,
    COUNT(*) as order_count
FROM orders
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY order_date
```

## 工具使用流程

### 标准分析流程

```
1. search_tables_by_keyword(keyword="业务关键词")
   ↓ 发现相关表列表
   
2. get_table_schema_details(table_name="主表")
   ↓ 理解表结构和外键关系
   
3. get_table_schema_details(table_name="子表")
   ↓ 确认关联字段
   
4. execute_safe_select(sql="聚合统计SQL")
   ↓ 执行查询获取结果
   
5. 格式化结果为表格展示
```

### 外键识别技巧

1. **查看 foreign_keys 数组**:
   ```json
   {
     "foreign_keys": [
       {
         "constraint_name": "fk_document_kb",
         "columns": ["knowledge_base_id"],
         "foreign_table": "knowledge_mgmt_knowledgebase",
         "foreign_columns": ["id"]
       }
     ]
   }
   ```

2. **识别外键字段命名模式**:
   - `parent_table_id`
   - `parent_table_name_id`
   - 通常以 `_id` 结尾

3. **利用列名推断**:
   - `knowledge_base_id` → 关联 `knowledge_base` 表
   - `user_id` → 关联 `user` 表

## SQL 聚合函数

### 常用聚合函数

| 函数                     | 用途           | 示例                      |
| ------------------------ | -------------- | ------------------------- |
| `COUNT(*)`               | 统计所有行数   | `COUNT(*)`                |
| `COUNT(column)`          | 统计非NULL行数 | `COUNT(id)`               |
| `COUNT(DISTINCT column)` | 统计唯一值数量 | `COUNT(DISTINCT user_id)` |
| `SUM(column)`            | 求和           | `SUM(amount)`             |
| `AVG(column)`            | 平均值         | `AVG(price)`              |
| `MIN(column)`            | 最小值         | `MIN(created_at)`         |
| `MAX(column)`            | 最大值         | `MAX(updated_at)`         |

### GROUP BY 规则

- 所有非聚合列都必须出现在 `GROUP BY` 中
- 示例:
  ```sql
  SELECT id, name, COUNT(*)  -- id和name是非聚合列
  FROM table
  GROUP BY id, name           -- 必须GROUP BY id, name
  ```

## 常见错误和解决方案

### 错误1: 重复计数

**问题**: 多层JOIN导致COUNT结果翻倍
```sql
-- ❌ 错误: chunk_count会因为document的多条记录而重复计数
SELECT kb.id, COUNT(d.id), COUNT(c.id)
FROM kb
JOIN d ON d.kb_id = kb.id
JOIN c ON c.d_id = d.id
GROUP BY kb.id
```

**解决**: 使用 `COUNT(DISTINCT ...)`
```sql
-- ✅ 正确
SELECT kb.id, COUNT(DISTINCT d.id), COUNT(c.id)
FROM kb
LEFT JOIN d ON d.kb_id = kb.id
LEFT JOIN c ON c.d_id = d.id
GROUP BY kb.id
```

### 错误2: 缺少GROUP BY列

**问题**: 非聚合列未包含在GROUP BY中
```sql
-- ❌ 错误: name不在GROUP BY中
SELECT id, name, COUNT(*)
FROM table
GROUP BY id
```

**解决**: 添加所有非聚合列
```sql
-- ✅ 正确
SELECT id, name, COUNT(*)
FROM table
GROUP BY id, name
```

### 错误3: JOIN导致数据丢失

**问题**: 使用INNER JOIN导致没有子记录的父记录被过滤
```sql
-- ❌ 可能丢失没有document的knowledge_base
SELECT kb.id, COUNT(d.id)
FROM knowledge_base kb
INNER JOIN document d ON d.kb_id = kb.id
GROUP BY kb.id
```

**解决**: 使用LEFT JOIN
```sql
-- ✅ 保留所有knowledge_base
SELECT kb.id, COUNT(d.id)
FROM knowledge_base kb
LEFT JOIN document d ON d.kb_id = kb.id
GROUP BY kb.id
```

## 表格化输出建议

执行查询后,应将结果格式化为Markdown表格:

```markdown
| 知识库ID | 知识库名称 | 文档数 | 分块数 |
| -------- | ---------- | ------ | ------ |
| 1        | 技术文档   | 15     | 234    |
| 2        | 产品手册   | 8      | 156    |
```

## 总结

1. **先探索,后查询**: 先用搜索和schema工具理解数据结构
2. **理解关系**: 通过外键理解表之间的层级关系
3. **聚合统计**: 使用COUNT/SUM配合GROUP BY进行统计
4. **注意JOIN类型**: LEFT JOIN保留所有父记录
5. **避免重复计数**: 多层JOIN时使用DISTINCT
6. **安全第一**: 始终明确指定列名,避免敏感字段
