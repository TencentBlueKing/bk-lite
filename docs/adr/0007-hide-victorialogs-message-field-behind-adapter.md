# ADR 0007：把 VictoriaLogs 主消息字段封装在适配器内

Status: accepted

日志采集器、NATS 事件、日志提取器和查询界面统一把 `message` 作为唯一日志正文；
VictoriaLogs 的 `_msg` 只作为存储引擎物理字段存在。中心 Vector 在所有提取规则执行后
使用移动语义把 `message` 变为 `_msg`，查询适配器再把 `_msg` 移回 `message`，因此不会
为兼容存储同时保存两份完整正文。

直接让所有模块使用 `_msg` 会把 VictoriaLogs 的实现约束扩散到采集插件和产品接口；
直接让 VictoriaLogs 接收 `message` 虽然配置更短，但不能从发送事件本身证明原字段未被
作为普通属性保留。显式的最终写入适配器多一个 transform，却能在 Vector 事件上验证
“写入前只有 `message`、写入后只有 `_msg`”这一不变量。

混合版本期间，中心归一化模块把已知旧字段移动到 `message` 并删除别名；SNMP 以去掉
syslog 头后的 `trap_message` 为正文，其他冲突优先保留已有 `message`。历史日志不回填，
查询适配器在读取时隐藏旧别名。回滚代码不会改写历史数据，但回退到旧中心配置会重新
暴露旧采集器的重复字段，因此发布顺序必须是中心归一化先于采集器模板。旧中心不
理解仅含 `message` 的新事件，回滚时必须先回退采集器，再回退中心。
