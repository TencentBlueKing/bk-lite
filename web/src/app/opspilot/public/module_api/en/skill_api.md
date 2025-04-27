# Skill API

## API Description

Provides external interfaces for skills, allowing users to utilize skills through API calls.

## API Examples

### 1. Get Skill List

**Request Parameters**

Query：

| Parameter Name | Required | Example | Description |
|---------------|----------|----------|-------------|
| name          | No       | Skill1   | Search keyword |
| page_size     | Yes      | 10       | Items per page |
| page          | Yes      | 1        | Current page number |

**Response Data**

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
          "guest"
        ],
        "created_by": "1406489435@qq.com",
        "updated_by": "1406489435@qq.com",
        "name": "hello",
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

**Field Descriptions**

- `result`: `true` indicates whether the request was successful.
- `code`: `"20000"` status code indicating success.
- `message`: `"success"` description of the request result.
- `data`: Data object containing specific return data.
  - `count`: `1` number of returned items.
  - `items`: `[...]` array of data entries containing specific record information.
    - `id`: `10` unique identifier for the object.
    - `team_name`: `["guest"]` array of team names the object belongs to.
    - `created_by`: `"1406489435@qq.com"` email address of the creator.
    - `updated_by`: `"1406489435@qq.com"` email address of the last updater.
    - `name`: `"hello"` name.
    - `skill_id`: `null` skill identifier, currently empty.
    - `skill_prompt`: `null` skill prompt, currently empty.
    - `enable_conversation_history`: `false` boolean indicating if conversation history is enabled.
    - `conversation_window_size`: `10` specifies the size of the conversation window.
    - `enable_rag`: `false` boolean indicating if RAG is enabled.
    - `enable_rag_knowledge_source`: `false` boolean indicating if RAG knowledge source is enabled.
    - `rag_score_threshold`: `0.7` RAG score threshold for knowledge inclusion.
    - `introduction`: `"56"` record introduction.
    - `team`: `["8bb5627e-3a25-45b9-850b-62d570a9282b"]` team's unique identifier.
    - `llm_model`: `null` language model identifier.
    - `knowledge_base`: `[]` knowledge base array, currently empty.

### 2. Test Skill

**Request Parameters**

Headers：

| Parameter Name | Value            | Required | Example | Description |
|---------------|------------------|----------|---------|-------------|
| Content-Type  | application/json | Yes      |         |             |

Query：

| Parameter Name | Required | Example | Description |
|---------------|----------|----------|-------------|
| name          | No       | Skill1   | Search keyword |
| page_size     | Yes      | 10       | Items per page |
| page          | Yes      | 1        | Current page number |

Body:

~~~json
{
  "user_message": "hello", // User message
  "llm_model": 1, // Large model ID
  "skill_prompt": "abc", // Prompt
  "enable_rag": true, // Enable RAG
  "enable_rag_knowledge_source": true, // Show RAG knowledge source
  "rag_score_threshold": [{"knowledge_base": 1, "score": 0.7}], // RAG score threshold
  "chat_history": [{"event": "user", "text": "abc"}, {"event": "bot", "text": "ab"}], // Chat history
  "conversation_window_size": 10, // Conversation window size
  "temperature": 0.7,
  "show_think": true, // Show thinking content
  "tools": ["shell", "duckduckgo-search", "prometheus-search"] // Currently only these three are supported
}
~~~

**Response Data**

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
          "guest"
        ],
        "created_by": "1406489435@qq.com",
        "updated_by": "1406489435@qq.com",
        "name": "hello",
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

**Field Descriptions**

- `result`: `true` indicates whether the request was successful.
- `code`: `"20000"` status code indicating success.
- `message`: `"success"` description of the request result.
- `data`: Data object containing specific return data.
  - `count`: `1` number of returned items.
  - `items`: `[...]` array of data entries containing specific record information.
    - `id`: `10` unique identifier for the object.
    - `team_name`: `["guest"]` array of team names the object belongs to.
    - `created_by`: `"1406489435@qq.com"` email address of the creator.
    - `updated_by`: `"1406489435@qq.com"` email address of the last updater.
    - `name`: `"hello"` name.
    - `skill_id`: `null` skill identifier, currently empty.
    - `skill_prompt`: `null` skill prompt, currently empty.
    - `enable_conversation_history`: `false` boolean indicating if conversation history is enabled.
    - `conversation_window_size`: `10` specifies the size of the conversation window.
    - `enable_rag`: `false` boolean indicating if RAG is enabled.
    - `enable_rag_knowledge_source`: `false` boolean indicating if RAG knowledge source is enabled.
    - `rag_score_threshold`: `0.7` RAG score threshold for knowledge inclusion.
    - `introduction`: `"56"` record introduction.
    - `team`: `["8bb5627e-3a25-45b9-850b-62d570a9282b"]` team's unique identifier.
    - `llm_model`: `null` language model identifier.
    - `knowledge_base`: `[]` knowledge base array, currently empty.
