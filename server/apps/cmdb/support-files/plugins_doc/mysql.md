## 说明
该插件通过 MySQL 原生协议直连实例，读取版本与关键配置项，并标准化同步至 CMDB。
---

## 操作入口与执行位置（重要）
你需要在 CMDB Web 页面完成配置：
1. 进入“CMDB → 资产管理 → 自动发现 → 采集 → 专业采集”。
2. 在插件卡片中选择 **MySQL**。
3. 点击“新增任务”，按本 SOP 填写并保存。

说明：任务实际执行发生在你选择的“接入点”上；文档中的连通性自测命令，均应在接入点机器上执行。

---

## 前置要求（你需要准备的事项）
1. 网络连通：接入点能访问 MySQL 实例的 `3306/TCP`（或你设置的端口）。
2. 采集账号：建议创建一个专用于采集的账号（只读/查询为主）。
3. 连接参数：目标实例的 IP（或域名）、端口、用户名、密码。

---

## 步骤 1：网络连通性自测（在接入点执行）
任选一种方式进行验证：

- Linux：
  - `nc -vz <mysql_ip> 3306`
  - `mysql -h <mysql_ip> -P 3306 -u <user> -p -e "SELECT 1;"`

- Windows PowerShell：
  - `Test-NetConnection <mysql_ip> -Port 3306`

判断标准：端口连通，且能够成功执行 `SELECT 1`。

---

## 步骤 2：创建采集账号（在目标 MySQL 上执行）
下面提供推荐模板（尽量不授予写入权限）。不同 MySQL 版本/安全策略可能略有差异；如遇“权限不足”，请按“常见问题排查”处理。

### 推荐权限模板（通用）
```sql
-- 1) 创建账号（把用户名/密码替换成你自己的）
CREATE USER 'cmdb_collector'@'%' IDENTIFIED BY 'YourStrongPassword';

-- 2) 允许读取 information_schema（用于获取部分配置/状态）
GRANT SELECT ON information_schema.* TO 'cmdb_collector'@'%';

-- 3) 获取部分全局信息时可能需要的查询权限（不涉及写入）
GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'cmdb_collector'@'%';

FLUSH PRIVILEGES;
```

### 可选：限制登录来源（更安全）
如果你不希望 `@'%'`，可以把 `%` 改成接入点 IP：
```sql
CREATE USER 'cmdb_collector'@'10.0.0.10' IDENTIFIED BY 'YourStrongPassword';
```

---

## 步骤 3：在 CMDB 上创建采集任务（页面操作）
进入“CMDB → 资产管理 → 自动发现 → 采集 → 专业采集”，选择 MySQL 插件后：

1. 点击“新增任务”。
2. 基本配置：填写任务名称、周期（建议先用较短周期验证）、超时时间、组织、接入点。
3. 采集对象（二选一）：
   - IP 范围：填写起止 IP（用于批量发现）。
   - 选择资产：从资产列表选择目标实例（适用于已在 CMDB 中维护 MySQL 实例资产的场景）。
4. 凭据：填写用户名（`user`）、密码（`password`）、端口（`port`）。
5. 保存后，可在列表中点击“同步”（立即执行）做一次验证。

---

## 步骤 4：验收（如何判断配置成功）
1. 任务列表中执行状态变为“成功”。
2. 点“详情”可查看最近一次采集结果概览/时间。
3. 在资产数据中能看到对应 MySQL 实例的关键字段被写入/更新。

---

## 关键字段说明（避免误解）
- `mysql.ip_addr`：**不是**从数据库内部“推断出来”的 IP，而是你选择的目标实例（IP 范围或资产管理 IP）对应的地址。
- `mysql.version`：通常来自 `SELECT VERSION()` 或等价方式；不一定等同于某个 `SHOW VARIABLES` 单项。
- `mysql.bind_address`：来自实例配置（变量 `bind_address`），可能是 `0.0.0.0`，这不代表真实对外 IP。

---

## 常见问题排查
1. 端口不通/超时：优先检查接入点到 MySQL 的网络路径（安全组/防火墙/路由），再检查 MySQL 是否监听在目标端口。
2. 认证失败：确认用户名/密码、账号来源（`@'%'` 或指定来源 IP）以及是否启用密码策略。
3. 权限不足：
   - 报错提示涉及 `performance_schema` 时，可补充：`GRANT SELECT ON performance_schema.* TO 'cmdb_collector'@'%';`
   - 如报错涉及其它系统库或全局信息读取权限，请在安全评估后再补充相应只读权限（避免一次性给过大权限）。

---

## 安全建议
1. 采集账号仅用于采集，避免复用业务账号。
2. 优先限制账号来源（仅允许接入点 IP）。
3. 密码不要通过聊天/工单明文传播；推荐由负责人创建后安全交付，并定期轮换。

## 采集内容
| Key 名称 | 含义 |
| :----------- | :--- |
| mysql.ip_addr | 实例 IP |
| mysql.port | 监听端口 |
| mysql.version | MySQL 版本 |
| mysql.enable_binlog | 是否开启 binlog (log_bin) |
| mysql.sync_binlog | binlog 同步策略 (sync_binlog) |
| mysql.max_conn | 最大连接数 (max_connections) |
| mysql.max_mem | 单包最大大小 (max_allowed_packet) |
| mysql.basedir | 安装目录 (basedir) |
| mysql.datadir | 数据目录 (datadir) |
| mysql.socket | 本地 socket 文件 |
| mysql.bind_address | 绑定地址 (bind_address) |
| mysql.slow_query_log | 慢查询日志是否开启 |
| mysql.slow_query_log_file | 慢查询日志文件路径 |
| mysql.log_error | 错误日志文件路径 |
| mysql.wait_timeout | 空闲连接等待超时 (wait_timeout) |