# FreeBSD os_monitor 输出契约

本目录锁定远程 sh 脚本的 JSON 输出，以及到 Prometheus 文本的映射。不是测试树。

| 文件 | 含义 |
| --- | --- |
| `os_monitor.sample.json` | 脚本标准 JSON 输出（含带引号与空格的挂载点） |
| `os_monitor.prometheus.txt` | `parse_freebsd_metrics_to_prometheus` 对应输出：`instance_id=sample-1`，`os_type=freebsd`，`timestamp=1700000000000` |
| `df.special.sample.txt` | `df -kT` 特殊挂载点输入 |
| `disk.special.expected.json` | 上一文件经脚本磁盘段解析后应得到的 `disk` 数组；必须能被 `json.loads` 接受 |

挂载点、网卡名、设备名等字符串由脚本内 `json_esc` 转义后再写入 JSON，避免引号、反斜杠或控制字符破坏整段输出。
