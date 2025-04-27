# 技能API调用

## API调用说明

提供技能的对外接口，用户可以调用接口实现技能的使用。

## API调用示例

### 1. 获取技能列表

**请求参数**

Query：

| 参数名称   | 是否必须 | 示例   | 备注      |
|------------|----------|--------|-----------|
| name       | 否       | 技能1  | 搜索关键词 |
| page_size  | 是       | 10     | 每页条数   |
| page       | 是       | 1      | 当前页码   |

**返回数据**

~~~json
{
  "result": true,
  "code": "20000",
  "message": "success",
  "data": {
    "count": 1,
    "items": [
      {
        "id": 10,
        "team_name": [
          "游客"
        ],
        "created_by": "1406489435@qq.com",
        "updated_by": "1406489435@qq.com",
        "name": "你好hello",
        "skill_id": null,
        "skill_prompt": null,
        "enable_conversation_history": false,
        "conversation_window_size": 10,
        "enable_rag": false,
        "enable_rag_knowledge_source": false,
        "rag_score_threshold": 0.7,
        "introduction": "56",
        "team": [
          "8bb5627e-3a25-45b9-850b-62d570a9282b"
        ],
        "llm_model": null,
        "knowledge_base": []
      }
    ]
  }
}
~~~

**字段说明**

- `result`: `true` 指示请求是否成功。
- `code`: `"20000"` 状态码，表示请求成功。
- `message`: `"success"` 请求结果的描述信息。
- `data`: 数据对象，包含具体的返回数据。
  - `count`: `1` 返回的条目数量。
  - `items`: `[...]` 数据条目的数组，包含具体的记录信息。
    - `id`: `10` 唯一标识符，表示该对象的 ID。
    - `team_name`: `["游客"]` 团队名称的数组，表示该对象所属的团队。
    - `created_by`: `"1406489435@qq.com"` 创建该记录的用户的邮箱地址。
    - `updated_by`: `"1406489435@qq.com"` 最后更新该记录的用户的邮箱地址。
    - `name`: `"你好hello"` 名称。
    - `skill_id`: `null` 技能标识符，当前为空，表示没有关联技能。
    - `skill_prompt`: `null` 技能提示，当前为空，表示没有关联技能提示。
    - `enable_conversation_history`: `false` 布尔值，指示是否启用对话历史。
    - `conversation_window_size`: `10` 指定对话窗口的大小，即可回顾的聊天记录条数。
    - `enable_rag`: `false` 布尔值，指示是否启用 RAG（Retrieval-Augmented Generation）。
    - `enable_rag_knowledge_source`: `false` 布尔值，指示是否启用 RAG 知识来源。
    - `rag_score_threshold`: `0.7` RAG 分数阈值，决定哪些知识被纳入对话中。
    - `introduction`: `"56"` 记录的简介信息。
    - `team`: `["8bb5627e-3a25-45b9-850b-62d570a9282b"]` 团队的唯一标识 ID，用于关联团队。
    - `llm_model`: `null` 大语言模型的标识符，当前为空。
    - `knowledge_base`: `[]` 知识库的数组，当前为空，表示没有关联的知识内容。

### 2. 技能测试

**请求参数**

Headers：

| 参数名称     | 参数值            | 是否必须 | 示例               | 备注 |
|--------------|-------------------|----------|--------------------|------|
| Content-Type | application/json  | 是       |                    |      |

Query：

| 参数名称  | 是否必须 | 示例   | 备注      |
|-----------|----------|--------|-----------|
| name      | 否       | 技能1  | 搜索关键词 |
| page_size | 是       | 10     | 每页条数   |
| page      | 是       | 1      | 当前页码   |

Body:

~~~json
{
  "user_message": "你好", // 用户消息
  "llm_model": 1, // 大模型ID
  "skill_prompt": "abc", // Prompt
  "enable_rag": true, // 是否启用RAG
  "enable_rag_knowledge_source": true, // 是否显示RAG知识来源
  "rag_score_threshold": [{"knowledge_base": 1, "score": 0.7}], // RAG分数阈值
  "chat_history": [{"event": "user", "text": "abc"}, {"event": "bot", "text": "ab"}], // 对话历史
  "conversation_window_size": 10, // 对话窗口大小
  "temperature": 0.7,
  "show_think": true, // 展示think内容
  "tools": ["shell", "duckduckgo-search", "prometheus-search"] // 目前只支持这三种
}
~~~

**字段说明**

- `user_message`: `"你好"` 用户消息，表示传递给大模型的信息。
- `llm_model`: `1` 大模型ID，表示选择的大语言模型的标识符。
- `skill_prompt`: `"abc"` Prompt，用于引导大语言模型的提示信息。
- `enable_rag`: `true` 布尔值，指示是否启用RAG（Retrieval-Augmented Generation）。
- `enable_rag_knowledge_source`: `true` 布尔值，指示是否显示RAG知识来源。
- `rag_score_threshold`: `[{"knowledge_base": 1, "score": 0.7}]` RAG分数阈值，包含知识库ID和分数的数组。
- `chat_history`: `[{"event": "user", "text": "abc"}, {"event": "bot", "text": "ab"}]` 对话历史，包含用户和机器人的聊天记录。
- `conversation_window_size`: `10` 对话窗口大小，即可回顾的聊天记录条数。
- `temperature`: `0.7` 大语言模型生成文本时的温度参数，控制输出的随机性。
- `show_think`: `true` 布尔值，指示是否展示think内容，`false` 时不展示思考过程。
- `tools`: `["shell", "duckduckgo-search", "prometheus-search"]` 工具的数组，目前支持shell, duckduckgo-search, prometheus-search。

**返回数据**

~~~json
{
  "result": true,
  "code": "20000",
  "message": "success",
  "data": {
    "count": 1,
    "items": [
      {
        "id": 10,
        "team_name": [
          "游客"
        ],
        "created_by": "1406489435@qq.com",
        "updated_by": "1406489435@qq.com",
        "name": "你好hello",
        "skill_id": null,
        "skill_prompt": null,
        "enable_conversation_history": false,
        "conversation_window_size": 10,
        "enable_rag": false,
        "enable_rag_knowledge_source": false,
        "rag_score_threshold": 0.7,
        "introduction": "56",
        "team": [
          "8bb5627e-3a25-45b9-850b-62d570a9282b"
        ],
        "llm_model": null,
        "knowledge_base": []
      }
    ]
  }
}
~~~

**字段说明**

- `result`: `true` 指示请求是否成功。
- `code`: `"20000"` 状态码，表示请求成功。
- `message`: `"success"` 请求结果的描述信息。
- `data`: 数据对象，包含具体的返回数据。
  - `count`: `1` 返回的条目数量。
  - `items`: `[...]` 数据条目的数组，包含具体的记录信息。
    - `id`: `10` 唯一标识符，用于标识该数据对象。
    - `team_name`: `["游客"]` 团队名称的数组，表示该记录所属的团队是“游客”。
    - `created_by`: `"1406489435@qq.com"` 创建用户的邮箱地址。
    - `updated_by`: `"1406489435@qq.com"` 最后更新该记录的用户的邮箱地址。
    - `name`: `"你好hello"` 名称，表明这是一个对话主题或标识。
    - `skill_id`: `null` 技能标识符，当前为空，表示此记录并未指定任何技能。
    - `skill_prompt`: `null` 技能提示，当前为空，表示没有为该记录提供技能提示。
    - `enable_conversation_history`: `false` 布尔值，指示是否启用对话历史记录。
    - `conversation_window_size`: `10` 对话窗口大小，即可回顾的聊天记录条数。
    - `enable_rag`: `false` 布尔值，指示是否启用 RAG（Retrieval-Augmented Generation）。
    - `enable_rag_knowledge_source`: `false` 布尔值，指示是否启用 RAG 知识来源。
    - `rag_score_threshold`: `0.7` RAG 分数阈值，决定哪些知识会被纳入对话中。
    - `introduction`: `"56"` 记录的简介信息。
    - `team`: `["8bb5627e-3a25-45b9-850b-62d570a9282b"]` 团队的唯一标识 ID，用于关联团队。
    - `llm_model`: `null` 大语言模型的标识符，当前为空。
    - `knowledge_base`: `[]` 知识库的数组，当前为空，表示没有关联的知识内容。