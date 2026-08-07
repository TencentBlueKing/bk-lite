
### LogsQL Query Syntax



#### 1 Simple Queries

- **Basic Query**: Enter keywords directly to search log messages. For example:
  ```logs
  error
  ```
  This query will return all logs containing the `error` keyword.

- **Keyword Conflicts**: If query terms conflict with LogsQL keywords, wrap them in double quotes. For example:
  ```logs
  "and"
  ```

- **Multi-word Phrase Query**: Phrases can be searched by wrapping them in quotes. For example:
  ```logs
  "error: cannot find file"
  ```


#### 2 Log Sorting
- Sort by time:
  ```logs
  _time:5m error | sort by (_time)
  ```

- Sort by time in descending order and limit the number of returned logs (e.g., return the latest 10 logs):
  ```logs
  _time:5m error | sort by (_time) desc | limit 10
  ```

#### 3 Specify Return Fields
- Return only specified fields (e.g., `_time`, `_stream`, and `message`):
  ```logs
  error _time:5m | fields _time, _stream, message
  ```

#### 4 Exclude Specific Logs
- Use the `NOT` operator to exclude specific logs. For example, exclude logs containing `buggy_app`:
  ```logs
  _time:5m error NOT buggy_app
  ```

- Simplified syntax, use `-` instead of `NOT`:
  ```logs
  _time:5m error -buggy_app
  ```

- Exclude logs with multiple conditions (e.g., `buggy_app` and `foobar`):
  ```logs
  _time:5m error -buggy_app -foobar
  ```

- Use parentheses and `OR` operator for better readability:
  ```logs
  _time:5m error -(buggy_app OR foobar)
  ```

#### 5 Field-level Queries
- Query keywords in specific fields (e.g., `log.level`):
  ```logs
  _time:5m log.level:error -(buggy_app OR foobar)
  ```

- If field names or keywords contain special characters, wrap them in double quotes. For example:
  ```logs
  "_time":"5m" "log.level":"error" -("buggy_app" OR "foobar")
  ```
