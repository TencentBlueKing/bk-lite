# language: zh-CN
功能: 本地 SCP 传输执行
  为了让运维人员能直接判断传输结果
  作为本地执行器的使用者
  我希望成功输出和失败诊断都能被完整保留

  背景:
    假如 存在一个本地 SCP 执行器实例

  场景: 成功传输时会合并 stdout 与 stderr
    假如 执行请求为:
      | 字段            | 值                                                                        |
      | shell           | sh                                                                        |
      | command         | printf 'copied'; printf ' stderr-note' 1>&2 # scp                         |
      | log_context     | upload root@10.0.0.1:22 /tmp/a -> /tmp/b [auth=password kind=file size=6B name=a] |
      | execute_timeout | 3                                                                         |
    当 在本地执行该命令
    那么 执行成功
    而且 组合输出包含 "copied"
    而且 组合输出包含 "stderr-note"

  场景: 传输超时时返回 timeout 错误码
    假如 执行请求为:
      | 字段            | 值             |
      | shell           | sh             |
      | command         | sleep 2 # scp  |
      | log_context     | upload timeout |
      | execute_timeout | 1              |
    当 在本地执行该命令
    那么 执行失败且错误码为 "timeout"
    而且 错误信息包含 "timed out"

  场景: Host key 校验失败时保留诊断输出
    假如 执行请求为:
      | 字段            | 值                                                  |
      | shell           | sh                                                  |
      | command         | printf 'Host key verification failed'; exit 1 # scp |
      | log_context     | download host-key                                   |
      | execute_timeout | 3                                                   |
    当 在本地执行该命令
    那么 执行失败且错误码为 "execution_failure"
    而且 组合输出包含 "Host key verification failed"
    而且 错误信息包含 "exit code 1"

  场景: 认证失败时保留 Permission denied 输出
    假如 执行请求为:
      | 字段            | 值                                       |
      | shell           | sh                                       |
      | command         | printf 'Permission denied'; exit 1 # scp |
      | log_context     | download auth-failure                    |
      | execute_timeout | 3                                        |
    当 在本地执行该命令
    那么 执行失败且错误码为 "execution_failure"
    而且 组合输出包含 "Permission denied"
    而且 错误信息包含 "exit code 1"

  场景: 缺少 sshpass 时保留诊断输出
    假如 执行请求为:
      | 字段            | 值                                             |
      | shell           | sh                                             |
      | command         | printf 'sshpass: command not found'; exit 127 # scp |
      | log_context     | download missing-sshpass                       |
      | execute_timeout | 3                                              |
    当 在本地执行该命令
    那么 执行失败且错误码为 "execution_failure"
    而且 组合输出包含 "sshpass: command not found"
    而且 错误信息包含 "exit code 127"

  场景: 远端路径不存在时保留路径相关报错
    假如 执行请求为:
      | 字段            | 值                                                |
      | shell           | sh                                                |
      | command         | printf 'No such file or directory'; exit 1 # scp  |
      | log_context     | download missing-path                             |
      | execute_timeout | 3                                                 |
    当 在本地执行该命令
    那么 执行失败且错误码为 "execution_failure"
    而且 组合输出包含 "No such file or directory"
    而且 错误信息包含 "exit code 1"
