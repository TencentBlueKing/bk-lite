# 知识库API调用

## API调用示例

### 1. 查询知识库

**请求参数**

Query：

| 参数名称 | 是否必须 | 示例 | 备注 |
|----------|----------|------|------|
| name     | 否       | 12   |      |

**返回数据**

~~~json
{
  "result": true,
  "data": [
    {
      "id": 1,
      "team_name": [
        "admin"
      ],
      "created_at": "2024-09-04 15:52:21",
      "updated_at": "2024-09-04 15:52:21",
      "created_by": "admin",
      "updated_by": "",
      "name": "知识库测试",
      "introduction": "abcjde",
      "team": "2135b2b5-cbb4-4aea-8350-7329dcb6671a",
      "enable_vector_search": true,
      "vector_search_weight": 0.1,
      "enable_text_search": true,
      "text_search_weight": 0.9,
      "enable_rerank": false,
      "embed_model": 2,
      "rerank_model": 1
    }
  ]
}
~~~

**字段说明**

- `result`: ``true`` 请求是否成功，``true`` 为成功。
- `data`: ``[...]`` 数据条目的数组，包含具体的记录信息。
  - `id`: ``1`` 唯一标识符，表示该对象的 ID。
  - `team_name`: ``["admin"]`` 团队名称的数组，表示该对象所属的团队。
  - `created_at`: ``"2024-09-04 15:52:21"`` 创建时间。
  - `updated_at`: ``"2024-09-04 15:52:21"`` 最后更新时间。
  - `created_by`: ``"admin"`` 创建该记录的用户。
  - `updated_by`: ``""`` 最后更新该记录的用户。
  - `name`: ``"知识库测试"`` 知识库名称。
  - `introduction`: ``"abcjde"`` 知识库简介。
  - `team`: ``"2135b2b5-cbb4-4aea-8350-7329dcb6671a"`` 团队的唯一标识 ID，用于关联团队。
  - `enable_vector_search`: ``true`` 布尔值，指示是否启用向量搜索。
  - `vector_search_weight`: ``0.1`` 向量搜索权重，取值0.0~1.0。
  - `enable_text_search`: ``true`` 布尔值，指示是否启用文本搜索。
  - `text_search_weight`: ``0.9`` 文本搜索权重，取值0.0~1.0。
  - `enable_rerank`: ``false`` 布尔值，指示是否启用重新排序。
  - `embed_model`: ``2`` 嵌入模型的标识符。
  - `rerank_model`: ``1`` 重新排序模型的标识符。

### 2. 查询知识库文章

**请求参数**

Query：

| 参数名称            | 是否必须 | 示例  | 备注                           |
|---------------------|----------|-------|--------------------------------|
| knowledge_base_id   | 是       | 1     | 知识库ID                        |
| name                | 否       | aa    |                                |
| page                | 是       | 1     | 当前页码                       |
| page_size           | 是       | 1     | 每页条数                        |
| knowledge_source_type | 是    | file  | 知识来源类型，file, web_page, manual|
| train_status        | 否       | 0     | 0：正在训练，1: 训练完成，2： 训练失败|

**返回数据**

~~~json
{
  "result": true,
  "data": {
    "count": 11,
    "items": [
      {
        "name": "文章1.doc",
        "status": "Training",
        "chunk_size": 11,
        "created_at": "2021-12-12 12:12:12",
        "created_by": "admin"
      }
    ]
  }
}
~~~

**字段说明**

- `result`: ``true`` 请求是否成功。
- `data`: ``{...}`` 数据对象。
  - `count`: ``11`` 数据条目数量。
  - `items`: ``[...]`` 数据条目的数组，包含具体的记录信息。
    - `name`: ``"文章1.doc"`` 文章名称。
    - `status`: ``"Training"`` 文章状态。
    - `chunk_size`: ``11`` 文章分块大小。
    - `created_at`: ``"2021-12-12 12:12:12"`` 文章创建时间。
    - `created_by`: ``"admin"`` 创建该文章的用户。

### 3. 文件上传

**请求参数**

Headers：

| 参数名称     | 参数值            | 是否必须 | 示例               | 备注 |
|--------------|-------------------|----------|--------------------|------|
| Content-Type | application/json  | 是       |                    |      |

Query：

| 参数名称          | 是否必须 | 示例 | 备注                           |
|-------------------|----------|------|--------------------------------|
| knowledge_base_id | 是       | 1    | 知识库ID                       |
| name              | 否       | aa   |                                |
| page              | 是       | 1    | 当前页码                       |
| page_size         | 是       | 1    | 每页条数                        |
| source_type       | 是       | file | 知识来源类型，file, web_page, manual|

Body:

~~~json
{
  "knowledge_base_id": 1,
  "files": [] // 文件列表，以file的形式传参，多选
}
~~~

**返回数据**

~~~json
{
  "result": true,
  "data": [1, 2, 3, 4] // 文件的ID列表
}
~~~

**字段说明**

- `knowledge_base_id`: `1` 知识库的唯一标识符，用于与具体知识库关联。
- `files`: `[]` 文件列表，以 `file` 的形式传参，可以多选上传。
- `result`: ``true`` 请求是否成功。
- `data`: ``[1, 2, 3, 4]`` 文件的ID列表。

### 4. 新增网页

**请求参数**

Headers：

| 参数名称     | 参数值            | 是否必须 | 示例               | 备注 |
|--------------|-------------------|----------|--------------------|------|
| Content-Type | application/json  | 是       |                    |      |

Query：

| 参数名称          | 是否必须 | 示例 | 备注                           |
|-------------------|----------|------|--------------------------------|
| knowledge_base_id | 是       | 1    | 知识库ID                       |
| name              | 否       | aa   |                                |
| page              | 是       | 1    | 当前页码                       |
| page_size         | 是       | 1    | 每页条数                        |
| source_type       | 是       | file | 知识来源类型，file, web_page, manual|

Body:

~~~json
{
  "knowledge_base_id": 1,
  "name": "abcd",
  "url": "http://wewewe.wewe",
  "max_depth": 1
}
~~~

**返回数据**

~~~json
{
  "result": true,
  "data": 1 // 网页知识库的ID
}
~~~

**字段说明**

- `knowledge_base_id`: `1` 知识库的唯一标识符，用于与具体知识库关联。
- `name`: `"abcd"` 新增网页数据的名称。
- `url`: `"http://wewewe.wewe"` 网页地址的 URL。
- `max_depth`: `1` 网页爬取的最大深度，限制爬取范围。
- `result`: ``true`` 请求是否成功。
- `data`: ``1`` 新增网页的ID。

### 5. 新增自定义内容

**请求参数**

Headers：

| 参数名称     | 参数值            | 是否必须 | 示例               | 备注 |
|--------------|-------------------|----------|--------------------|------|
| Content-Type | application/json  | 是       |                    |      |

Query：

| 参数名称          | 是否必须 | 示例 | 备注                           |
|-------------------|----------|------|--------------------------------|
| knowledge_base_id | 是       | 1    | 知识库ID                       |
| name              | 否       | aa   |                                |
| page              | 是       | 1    | 当前页码                       |
| page_size         | 是       | 1    | 每页条数                        |
| source_type       | 是       | file | 知识来源类型，file, web_page, manual|

Body:

~~~json
{
  "knowledge_base_id": 1,
  "name": "abcd",
  "content": "abcd"
}
~~~

**返回数据**

~~~json
{
  "result": true,
  "data": 1 // 自定义内容的ID
}
~~~

**字段说明**

- `knowledge_base_id`: `1` 知识库的唯一标识符，用于与具体知识库关联。
- `name`: `"abcd"` 自定义内容的名称。
- `content`: `"abcd"` 自定义添加的内容，文本记录。
- `result`: ``true`` 请求是否成功。
- `data`: ``1`` 自定义内容的ID。

### 6. 知识库文章批量训练

**请求参数**

Headers：

| 参数名称     | 参数值            | 是否必须 | 示例               | 备注 |
|--------------|-------------------|----------|--------------------|------|
| Content-Type | application/json  | 是       |                    |      |

Query：

| 参数名称          | 是否必须 | 示例 | 备注                           |
|-------------------|----------|------|--------------------------------|
| knowledge_base_id | 是       | 1    | 知识库ID                       |
| name              | 否       | aa   |                                |
| page              | 是       | 1    | 当前页码                       |
| page_size         | 是       | 1    | 每页条数                        |
| source_type       | 是       | file | 知识来源类型，file, web_page, manual|

Body:

~~~json
{
  "knowledge_document_ids": [
    1,
    2,
    3
  ]
}
~~~

**返回数据**

~~~json
{
  "result": true
}
~~~

**字段说明**

- `knowledge_document_ids`: `[1, 2, 3]` 知识文档的 ID 列表，指定要训练的文档。
- `result`: ``true`` 请求是否成功。

### 7. 知识库文章Testing

**请求参数**

Headers：

| 参数名称     | 参数值            | 是否必须 | 示例               | 备注 |
|--------------|-------------------|----------|--------------------|------|
| Content-Type | application/json  | 是       |                    |      |

Body:

~~~json
{
  "knowledge_base_id": 1,
  "query": "",
  "embed_model": 1, // 所选的模型
  "enable_rerank": true, // 启用rerank
  "rerank_model": 1, // 所选的rerank_model
  "enable_text_search": true,
  "text_search_weight": 0.9, // 文本权重
  "enable_vector_search": true,
  "vector_search_weight": 0.1, // 混合权重
  "rag_k": 50, // 返回结果数量
  "rag_num_candidates": 1000, //候选数量
  "text_search_mode": "match" // match 模糊，match_phrase 完整匹配
}
~~~

**返回数据**

~~~json
{
  "result": true,
  "data": [
    {
      "id": 1,
      "name": "acb",
      "knowledge_source_type": "file",
      "created_by": "admin",
      "created_at": "2020-12-12 12:21:12",
      "content": "",
      "score": 1000,
    }   
  ]
}
~~~

**字段说明**

- `knowledge_base_id`: `1` 知识库的唯一标识符，用于与具体知识库关联。
- `query`: `""` 查询关键字。
- `embed_model`: `1` 指定特定嵌入模型的 ID。
- `enable_rerank`: `true` 是否启用重排序功能。
- `rerank_model`: `1` 重排序启用时所选的模型 ID。
- `enable_text_search`: `true` 是否启用文本搜索功能。
- `text_search_weight`: `0.9` 文本搜索的权重。
- `enable_vector_search`: `true` 是否启用向量搜索功能。
- `vector_search_weight`: `0.1` 向量搜索的权重。
- `rag_k`: `50` 返回结果的数量。
- `rag_num_candidates`: `1000` 候选结果数量。
- `text_search_mode`: `"match"` 文本搜索模式，`match` 表示模糊匹配，`match_phrase` 表示完整匹配。
  
- `result`: ``true`` 请求是否成功。
- `data`: ``[...]`` 数据条目的数组，包含具体的记录信息。
  - `id`: ``1`` 唯一标识符，表示该对象的 ID。
  - `name`: ``"acb"`` 文章名称。
  - `knowledge_source_type`: ``"file"`` 文章来源类型。
  - `created_by`: ``"admin"`` 创建该记录的用户。
  - `created_at`: ``"2020-12-12 12:21:12"`` 创建时间。
  - `content`: ``""`` 文章内容。
  - `score`: ``1000`` 文章评分。

### 8. 知识库文章块删除

**请求参数**

路径参数：

| 参数名称 | 示例 | 备注  |
|----------|------|-------|
| id       | 1    | 文档ID |

Headers：

| 参数名称     | 参数值            | 是否必须 | 示例               | 备注 |
|--------------|-------------------|----------|--------------------|------|
| Content-Type | application/json  | 是       |                    |      |

Query：

| 参数名称 | 是否必须 | 示例 | 备注 |
|----------|----------|------|------|
| search_text | 否       | 123  | 查询文本 |

Body:

~~~json
{
  "chunk_id": "35196cd0-bda7-49be-91f0-8b2983109685"
}
~~~

**返回数据**

~~~json
{
  "result": true
}
~~~

**字段说明**

- `chunk_id`: `"35196cd0-bda7-49be-91f0-8b2983109685"` 要删除的块的唯一标识符。
- `result`: ``true`` 请求是否成功。

### 9. 知识库文章配置调整

**请求参数**

Headers：

| 参数名称      | 参数值           | 是否必须 | 示例              | 备注 |
|---------------|------------------|----------|-------------------|------|
| Content-Type  | application/json | 是       |                   |      |

Query：

| 参数名称          | 是否必须 | 示例 | 备注                           |
|-------------------|----------|------|--------------------------------|
| knowledge_base_id | 是       | 1    | 知识库ID                       |
| name              | 否       | aa   |                                |
| page              | 是       | 1    | 当前页码                       |
| page_size         | 是       | 1    | 每页条数                        |
| source_type       | 是       | file | 知识来源类型，file, web_page, manual|

Body:

~~~json
{
  "preview": false, // 是否预览，预览为true的情况下会文档分块返回
  "knowledge_source_type": "file", // 本地文件：file, 网络链接： web_page, 自定义文本： manual
  "knowledge_document_ids": [1, 2, 3], // 文章ID列表，文件上传时是多个，其它两个为单数字列表
  "enable_general_parse": true, // 开启分块解析
  "general_parse_chunk_size": 256, // 块大小
  "general_parse_chunk_overlap": 32, // 分块重叠
  "enable_semantic_chunk_parse": true,
  "semantic_chunk_parse_embedding_model": 1,
  "enable_ocr_parse": true,
  "ocr_model": 1,
  "enable_excel_parse": true,
  "excel_header_row_parse": true,
  "excel_full_content_parse": false,
  "is_save_only": false  // 是否仅保存
}
~~~

**返回数据**

~~~json
{
  "result": true,
  "data": []
}
~~~

**字段说明**

- `preview`: `false` 是否预览，预览状态下文档会分块返回。
- `knowledge_source_type`: `"file"` 知识源类型，可选值为：本地文件（`file`）、网络链接（`web_page`）、自定义文本（`manual`）。
- `knowledge_document_ids`: `[1, 2, 3]` 知识文档的 ID 列表，设置训练或配置的文档。
- `enable_general_parse`: `true` 是否启用分块解析。
- `general_parse_chunk_size`: `256` 块大小，定义每块的最大字符数。
- `general_parse_chunk_overlap`: `32` 块重叠大小，定义块之间的重叠字符数。
- `enable_semantic_chunk_parse`: `true` 是否启用语义分块解析。
- `semantic_chunk_parse_embedding_model`: `1` 使用的语义嵌入模型 ID。
- `enable_ocr_parse`: `true` 是否启用 OCR（光学字符识别）解析。
- `ocr_model`: `1` OCR 模型的 ID。
- `enable_excel_parse`: `true` 是否启用 Excel 文件解析。
- `excel_header_row_parse`: `true` 是否仅解析 Excel 文件的标题行。
- `excel_full_content_parse`: `false` 是否解析 Excel 的完整内容。
- `is_save_only`: `false` 是否仅保存配置，`false` 表示执行配置调整。
  
- `result`: ``true`` 请求是否成功。
- `data`: ``[]`` 返回的数据，当前为空。
