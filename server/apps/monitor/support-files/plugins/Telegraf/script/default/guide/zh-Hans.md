# 脚本采集接入指南

在节点上执行自定义脚本，解析标准输出中的 Prometheus 文本并上报指标。接入前请先阅读输出格式、`$` 写法、执行用户和限制。

## 输出格式

标准输出必须是 Prometheus 文本，一行一个样本，例如：

```
demo_cpu_usage{cpu="0"} 12.5
```

最多 50 条。行尾时间戳会被忽略。不要输出 Influx 行协议或 `key=value`。

## 脚本中的 `$`

脚本正文里的 `$` 必须写成 `$$`。页面上的示例模板已经按此规则编写。例如：

- 环境变量：`$$KEY`、`$${KEY}`、`$$env:KEY`
- awk 字段：`$$5`、`$$i`
- PowerShell 变量：`$$cpu`

Python 使用 `os.environ.get("KEY")` 时不需要 `$`。

## 环境变量

在「环境变量」中填写 KEY 和 VALUE。脚本内读取方式：

- Linux：`$$KEY` 或 `$${KEY}`
- Windows：`$$env:KEY`
- Python：`os.environ.get("KEY")`

## 执行用户

Linux 默认执行用户是 `telegraf`。该用户必须存在于**采集端**（采集节点 / sidecar 容器），不是平台 Web 所在机器。若采集端没有 `telegraf`，请把「执行用户」改成采集端已有的非 root 用户，或在采集端创建该用户。不能以 root 运行。

Windows 以服务账号运行，执行用户不可修改。

## 保留标签

以下标签由平台写入；脚本即使输出同名标签也会被覆盖，请改用其它标签名：

`instance_id`、`instance_type`、`collect_type`、`config_type`、`plugin_id`、`agent_id`、`config_id`、`script`

## 限制

- 只能绑定操作系统类监控对象
- 采集间隔不能小于 60 秒
- 超时按采集间隔减 1 秒执行，不能更长
- Linux 上不能以 root 用户运行
- 解释器只能从白名单选择：Linux 为 `/bin/sh`、`/bin/bash`、`/usr/bin/python3`，Windows 为 `powershell.exe`、`cmd.exe`、`python.exe`
- 指标名不能以 `bklite_script_` 开头
