
### LogsQL 操作语法



#### 1 简单查询

- **基本查询**：直接输入关键词即可检索日志消息。例如：
  ```logs
  error
  ```
  上述查询将返回所有包含 `error` 关键字的日志。

- **关键词冲突**：如果查询词与 LogsQL 的关键字发生冲突，可以将其用双引号括起来。例如：
  ```logs
  "and"
  ```

- **多词短语查询**：短语可以用引号括起来进行查询。例如：
  ```logs
  "error: cannot find file"
  ```


#### 2 日志排序
- 按时间排序：
  ```logs
  _time:5m error | sort by (_time)
  ```

- 按时间降序排序并限制返回日志条数（如返回最近 10 条日志）：
  ```logs
  _time:5m error | sort by (_time) desc | limit 10
  ```

#### 3 指定返回字段
- 仅返回指定的字段（如 `_time`、`_stream` 和 `message`）：
  ```logs
  error _time:5m | fields _time, _stream, message
  ```

#### 4 排除特定日志
- 使用 `NOT` 操作符排除特定日志。例如，排除包含 `buggy_app` 的日志：
  ```logs
  _time:5m error NOT buggy_app
  ```

- 简化语法，使用 `-` 代替 `NOT`：
  ```logs
  _time:5m error -buggy_app
  ```

- 排除多个条件日志（如 `buggy_app` 和 `foobar`）：
  ```logs
  _time:5m error -buggy_app -foobar
  ```

- 使用括号和 `OR` 操作符提高可读性：
  ```logs
  _time:5m error -(buggy_app OR foobar)
  ```

#### 5 字段级查询
- 查询特定字段（如 `log.level`）中的关键词：
  ```logs
  _time:5m log.level:error -(buggy_app OR foobar)
  ```

- 如果字段名或关键词包含特殊字符，可用双引号包裹。例如：
  ```logs
  "_time":"5m" "log.level":"error" -("buggy_app" OR "foobar")
  ```
