# Knowledge Base API

## API Examples

### 1. Query Knowledge Base

**Request Parameters**

Query：

| Parameter Name | Required | Example | Description |
|---------------|----------|---------|-------------|
| name          | No       | 12      |             |

**Response Data**

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
      "name": "Knowledge Base Test",
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

**Field Descriptions**

- `result`: ``true`` indicates if the request was successful.
- `data`: ``[...]`` array of data entries containing specific records.
  - `id`: ``1`` unique identifier.
  - `team_name`: ``["admin"]`` array of team names the object belongs to.
  - `created_at`: ``"2024-09-04 15:52:21"`` creation time.
  - `updated_at`: ``"2024-09-04 15:52:21"`` last update time.
  - `created_by`: ``"admin"`` creator of the record.
  - `updated_by`: ``""`` last updater of the record.
  - `name`: ``"Knowledge Base Test"`` knowledge base name.
  - `introduction`: ``"abcjde"`` knowledge base introduction.
  - `team`: ``"2135b2b5-cbb4-4aea-8350-7329dcb6671a"`` team's unique identifier.
  - `enable_vector_search`: ``true`` boolean indicating if vector search is enabled.
  - `vector_search_weight`: ``0.1`` vector search weight (0.0~1.0).
  - `enable_text_search`: ``true`` boolean indicating if text search is enabled.
  - `text_search_weight`: ``0.9`` text search weight (0.0~1.0).
  - `enable_rerank`: ``false`` boolean indicating if reranking is enabled.
  - `embed_model`: ``2`` embedding model identifier.
  - `rerank_model`: ``1`` reranking model identifier.

### 2. Query Knowledge Base Articles

**Request Parameters**

Query：

| Parameter Name            | Required | Example  | Description                           |
|---------------------------|----------|----------|---------------------------------------|
| knowledge_base_id         | Yes      | 1        | Knowledge Base ID                     |
| name                      | No       | aa       |                                       |
| page                      | Yes      | 1        | Current page number                   |
| page_size                 | Yes      | 1        | Number of items per page              |
| knowledge_source_type     | Yes      | file     | Knowledge source type: file, web_page, manual |
| train_status              | No       | 0        | 0: Training, 1: Training completed, 2: Training failed |

**Response Data**

~~~json
{
  "result": true,
  "data": {
    "count": 11,
    "items": [
      {
        "name": "Article1.doc",
        "status": "Training",
        "chunk_size": 11,
        "created_at": "2021-12-12 12:12:12",
        "created_by": "admin"
      }
    ]
  }
}
~~~

**Field Descriptions**

- `result`: ``true`` indicates if the request was successful.
- `data`: ``{...}`` data object.
  - `count`: ``11`` number of data entries.
  - `items`: ``[...]`` array of data entries containing specific records.
    - `name`: ``"Article1.doc"`` article name.
    - `status`: ``"Training"`` article status.
    - `chunk_size`: ``11`` article chunk size.
    - `created_at`: ``"2021-12-12 12:12:12"`` article creation time.
    - `created_by`: ``"admin"`` creator of the article.

### 3. File Upload

**Request Parameters**

Headers：

| Parameter Name | Parameter Value     | Required | Example           | Description |
|----------------|---------------------|----------|-------------------|-------------|
| Content-Type   | application/json    | Yes      |                   |             |

Query：

| Parameter Name          | Required | Example | Description                           |
|-------------------------|----------|---------|---------------------------------------|
| knowledge_base_id       | Yes      | 1       | Knowledge Base ID                     |
| name                    | No       | aa      |                                       |
| page                    | Yes      | 1       | Current page number                   |
| page_size               | Yes      | 1       | Number of items per page              |
| source_type             | Yes      | file    | Knowledge source type: file, web_page, manual |

Body：

~~~json
{
  "knowledge_base_id": 1,
  "files": [] // List of files, passed as file, multiple selection allowed
}
~~~

**Response Data**

~~~json
{
  "result": true,
  "data": [1, 2, 3, 4] // List of file IDs
}
~~~

**Field Descriptions**

- `knowledge_base_id`: `1` unique identifier of the knowledge base.
- `files`: `[]` list of files, passed as `file`, multiple selection allowed.
- `result`: ``true`` indicates if the request was successful.
- `data`: ``[1, 2, 3, 4]`` list of file IDs.

### 4. Add Web Page

**Request Parameters**

Headers：

| Parameter Name | Parameter Value     | Required | Example           | Description |
|----------------|---------------------|----------|-------------------|-------------|
| Content-Type   | application/json    | Yes      |                   |             |

Query：

| Parameter Name          | Required | Example | Description                           |
|-------------------------|----------|---------|---------------------------------------|
| knowledge_base_id       | Yes      | 1       | Knowledge Base ID                     |
| name                    | No       | aa      |                                       |
| page                    | Yes      | 1       | Current page number                   |
| page_size               | Yes      | 1       | Number of items per page              |
| source_type             | Yes      | file    | Knowledge source type: file, web_page, manual |

Body：

~~~json
{
  "knowledge_base_id": 1,
  "name": "abcd",
  "url": "http://wewewe.wewe",
  "max_depth": 1
}
~~~

**Response Data**

~~~json
{
  "result": true,
  "data": 1 // ID of the web page knowledge base
}
~~~

**Field Descriptions**

- `knowledge_base_id`: `1` unique identifier of the knowledge base.
- `name`: `"abcd"` name of the new web page data.
- `url`: `"http://wewewe.wewe"` URL of the web page.
- `max_depth`: `1` maximum depth for web crawling.
- `result`: ``true`` indicates if the request was successful.
- `data`: ``1`` ID of the new web page.

### 5. Add Custom Content

**Request Parameters**

Headers：

| Parameter Name | Parameter Value     | Required | Example           | Description |
|----------------|---------------------|----------|-------------------|-------------|
| Content-Type   | application/json    | Yes      |                   |             |

Query：

| Parameter Name          | Required | Example | Description                           |
|-------------------------|----------|---------|---------------------------------------|
| knowledge_base_id       | Yes      | 1       | Knowledge Base ID                     |
| name                    | No       | aa      |                                       |
| page                    | Yes      | 1       | Current page number                   |
| page_size               | Yes      | 1       | Number of items per page              |
| source_type             | Yes      | file    | Knowledge source type: file, web_page, manual |

Body：

~~~json
{
  "knowledge_base_id": 1,
  "name": "abcd",
  "content": "abcd"
}
~~~

**Response Data**

~~~json
{
  "result": true,
  "data": 1 // ID of the custom content
}
~~~

**Field Descriptions**

- `knowledge_base_id`: `1` unique identifier of the knowledge base.
- `name`: `"abcd"` name of the custom content.
- `content`: `"abcd"` custom content added as text.
- `result`: ``true`` indicates if the request was successful.
- `data`: ``1`` ID of the custom content.

### 6. Batch Train Knowledge Base Articles

**Request Parameters**

Headers：

| Parameter Name | Parameter Value     | Required | Example           | Description |
|----------------|---------------------|----------|-------------------|-------------|
| Content-Type   | application/json    | Yes      |                   |             |

Query：

| Parameter Name          | Required | Example | Description                           |
|-------------------------|----------|---------|---------------------------------------|
| knowledge_base_id       | Yes      | 1       | Knowledge Base ID                     |
| name                    | No       | aa      |                                       |
| page                    | Yes      | 1       | Current page number                   |
| page_size               | Yes      | 1       | Number of items per page              |
| source_type             | Yes      | file    | Knowledge source type: file, web_page, manual |

Body：

~~~json
{
  "knowledge_document_ids": [
    1,
    2,
    3
  ]
}
~~~

**Response Data**

~~~json
{
  "result": true
}
~~~

**Field Descriptions**

- `knowledge_document_ids`: `[1, 2, 3]` list of knowledge document IDs to be trained.
- `result`: ``true`` indicates if the request was successful.

### 7. Knowledge Base Article Testing

**Request Parameters**

Headers：

| Parameter Name | Parameter Value     | Required | Example           | Description |
|----------------|---------------------|----------|-------------------|-------------|
| Content-Type   | application/json    | Yes      |                   |             |

Body：

~~~json
{
  "knowledge_base_id": 1,
  "query": "",
  "embed_model": 1, // Selected model
  "enable_rerank": true, // Enable rerank
  "rerank_model": 1, // Selected rerank model
  "enable_text_search": true,
  "text_search_weight": 0.9, // Text weight
  "enable_vector_search": true,
  "vector_search_weight": 0.1, // Mixed weight
  "rag_k": 50, // Number of results to return
  "rag_num_candidates": 1000, // Number of candidates
  "text_search_mode": "match" // match for fuzzy, match_phrase for exact match
}
~~~

**Response Data**

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
      "score": 1000
    }
  ]
}
~~~

**Field Descriptions**

- `knowledge_base_id`: `1` unique identifier of the knowledge base.
- `query`: `""` query keyword.
- `embed_model`: `1` ID of the selected embedding model.
- `enable_rerank`: `true` indicates if reranking is enabled.
- `rerank_model`: `1` ID of the selected rerank model.
- `enable_text_search`: `true` indicates if text search is enabled.
- `text_search_weight`: `0.9` weight of text search.
- `enable_vector_search`: `true` indicates if vector search is enabled.
- `vector_search_weight`: `0.1` weight of vector search.
- `rag_k`: `50` number of results to return.
- `rag_num_candidates`: `1000` number of candidates.
- `text_search_mode`: `"match"` text search mode, `match` for fuzzy match, `match_phrase` for exact match.

- `result`: ``true`` indicates if the request was successful.
- `data`: ``[...]`` array of data entries containing specific records.
  - `id`: ``1`` unique identifier.
  - `name`: ``"acb"`` article name.
  - `knowledge_source_type`: ``"file"`` type of knowledge source.
  - `created_by`: ``"admin"`` creator of the record.
  - `created_at`: ``"2020-12-12 12:21:12"`` creation time.
  - `content`: ``""`` article content.
  - `score`: ``1000`` article score.

### 8. Delete Knowledge Base Article Chunk

**Request Parameters**

Path Parameters：

| Parameter Name | Example | Description  |
|----------------|---------|--------------|
| id             | 1       | Document ID  |

Headers：

| Parameter Name | Parameter Value     | Required | Example           | Description |
|----------------|---------------------|----------|-------------------|-------------|
| Content-Type   | application/json    | Yes      |                   |             |

Query：

| Parameter Name | Required | Example | Description |
|----------------|----------|---------|-------------|
| search_text    | No       | 123     | Search text |

Body：

~~~json
{
  "chunk_id": "35196cd0-bda7-49be-91f0-8b2983109685"
}
~~~

**Response Data**

~~~json
{
  "result": true
}
~~~

**Field Descriptions**

- `chunk_id`: `"35196cd0-bda7-49be-91f0-8b2983109685"` unique identifier of the chunk to be deleted.
- `result`: ``true`` indicates if the request was successful.

### 9. Adjust Knowledge Base Article Configuration

**Request Parameters**

Headers：

| Parameter Name | Parameter Value     | Required | Example           | Description |
|----------------|---------------------|----------|-------------------|-------------|
| Content-Type   | application/json    | Yes      |                   |             |

Query：

| Parameter Name          | Required | Example | Description                           |
|-------------------------|----------|---------|---------------------------------------|
| knowledge_base_id       | Yes      | 1       | Knowledge Base ID                     |
| name                    | No       | aa      |                                       |
| page                    | Yes      | 1       | Current page number                   |
| page_size               | Yes      | 1       | Number of items per page              |
| source_type             | Yes      | file    | Knowledge source type: file, web_page, manual |

Body：

~~~json
{
  "preview": false, // Whether to preview, if true, the document will be returned in chunks
  "knowledge_source_type": "file", // Local file: file, Web link: web_page, Custom text: manual
  "knowledge_document_ids": [1, 2, 3], // List of article IDs, multiple for file upload, single for the other two
  "enable_general_parse": true, // Enable chunk parsing
  "general_parse_chunk_size": 256, // Chunk size
  "general_parse_chunk_overlap": 32, // Chunk overlap
  "enable_semantic_chunk_parse": true,
  "semantic_chunk_parse_embedding_model": 1,
  "enable_ocr_parse": true,
  "ocr_model": 1,
  "enable_excel_parse": true,
  "excel_header_row_parse": true,
  "excel_full_content_parse": false,
  "is_save_only": false  // Whether to save only
}
~~~

**Response Data**

~~~json
{
  "result": true,
  "data": []
}
~~~

**Field Descriptions**

- `preview`: `false` whether to preview, if true, the document will be returned in chunks.
- `knowledge_source_type`: `"file"` type of knowledge source, can be: local file (`file`), web link (`web_page`), custom text (`manual`).
- `knowledge_document_ids`: `[1, 2, 3]` list of knowledge document IDs for training or configuration.
- `enable_general_parse`: `true` whether to enable chunk parsing.
- `general_parse_chunk_size`: `256` chunk size, defines the maximum number of characters per chunk.
- `general_parse_chunk_overlap`: `32` chunk overlap size, defines the number of overlapping characters between chunks.
- `enable_semantic_chunk_parse`: `true` whether to enable semantic chunk parsing.
- `semantic_chunk_parse_embedding_model`: `1` ID of the semantic embedding model.
- `enable_ocr_parse`: `true` whether to enable OCR (Optical Character Recognition) parsing.
- `ocr_model`: `1` ID of the OCR model.
- `enable_excel_parse`: `true` whether to enable Excel file parsing.
- `excel_header_row_parse`: `true` whether to parse only the header row of the Excel file.
- `excel_full_content_parse`: `false` whether to parse the full content of the Excel file.
- `is_save_only`: `false` whether to save only, `false` means to execute the configuration adjustment.

- `result`: ``true`` indicates if the request was successful.
- `data`: ``[]`` returned data, currently empty.
