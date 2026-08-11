# NATS 包初始化连接超时排查手册

本文用于排查 Docker Compose 部署 BK-Lite 时，执行
`controller_package_init` 或 `collector_package_init` 上传内置包，因无法连接 NATS
而失败的问题。

典型日志如下：

```text
controller 文件初始化开始！
nats: encountered error
asyncio.exceptions.CancelledError
TimeoutError
NATS connect failed, servers=tls://***:***@nats:4222
```

## 1. 结论速查

这类错误通常不是 Controller 或 Collector 包损坏，而是上传包时无法访问 NATS
JetStream Object Store。实际调用链为：

```text
controller_package_init / collector_package_init
  -> package_version_upload
  -> PackageService.upload_file
  -> JetStreamService.connect
  -> get_nc_client
  -> tls://nats:4222
```

按以下顺序排查：

| 检查结果 | 主要原因 | 下一步 |
|---|---|---|
| NATS 为 `Exited` 或 `Restarting` | NATS 配置、证书或存储启动失败 | 查看 NATS 日志与配置检查结果 |
| Server 内无法解析 `nats` | Docker 网络或服务别名异常 | 检查两个容器的网络归属 |
| DNS 正常、TCP 4222 不通 | NATS 未监听、容器重启或网络异常 | 检查监听端口和 NATS 日志 |
| TCP 正常、TLS 握手失败 | CA、证书 SAN、证书有效期或协议不匹配 | 核对两端证书与 TLS 配置 |
| TLS 正常、NATS 客户端报认证错误 | 用户名、密码或权限不匹配 | 核对环境注入和 NATS authorization |
| NATS 可连接、Object Store 初始化失败 | JetStream 未启用或存储不可用 | 检查 JetStream 配置与存储日志 |

## 2. 排查前注意事项

- 在包含最终 `docker-compose.yaml` 的部署目录执行本文命令。
- 如果现场使用旧版命令，将 `docker compose` 替换为 `docker-compose`。
- 不要把 `.env`、用户名、密码、Token、私钥或完整连接 URL 粘贴到工单。
- 不要删除 NATS volume，不要直接重生成证书；这些操作可能导致历史对象丢失或
  所有客户端同时断连。
- 不要通过延长连接超时、增加固定 `sleep` 或无限重试掩盖故障。

本文第 3 至第 8 节均为只读检查。第 9 节包含会改变容器状态或重新上传对象的恢复
操作，确认根因后再执行。

## 3. 确认容器运行状态

```bash
docker compose ps -a nats server
docker compose logs --since=30m --tail=300 nats
docker compose logs --since=30m --tail=200 server
```

查看 NATS 的退出状态和重启次数：

```bash
docker inspect \
  --format 'status={{.State.Status}} restart={{.RestartCount}} exit={{.State.ExitCode}} error={{.State.Error}}' \
  "$(docker compose ps -q nats)"
```

重点关注 NATS 日志中的以下内容：

- `error parsing config`、`unknown field`：配置文件不兼容或语法错误。
- `error loading certificate`、`no such file`、`permission denied`：证书挂载或权限错误。
- `address already in use`：4222 或其他监听端口冲突。
- `JetStream failed to start`、`storage directory`：JetStream 存储或 volume 异常。
- 容器不断出现新的启动横幅：NATS 正在重启循环。

如果 NATS 不是稳定的 `Up` 状态，先处理其启动错误，不要继续重试包初始化。

## 4. 检查 Server 与 NATS 的 Docker 网络

分别查看两个容器加入的网络：

```bash
docker inspect \
  --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' \
  "$(docker compose ps -q server)"

docker inspect \
  --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' \
  "$(docker compose ps -q nats)"
```

两个输出必须至少有一个共同网络，标准 Compose 部署通常是 `bklite-prod`。

再检查 NATS 在共同网络中的别名：

```bash
docker inspect \
  --format '{{json .NetworkSettings.Networks}}' \
  "$(docker compose ps -q nats)"
```

输出的 `Aliases` 中应包含 `nats`。如果两个容器没有共同网络，或不存在 `nats`
别名，Server 中的 `tls://nats:4222` 无法正常解析。

## 5. 从 Server 容器验证 DNS 和 TCP

以下脚本不读取或输出 NATS 凭据：

```bash
docker compose exec -T server python - <<'PY'
import signal
import socket


def timeout_handler(_signum, _frame):
    raise TimeoutError("DNS lookup timed out after 5 seconds")


signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(5)
try:
    addresses = socket.getaddrinfo("nats", 4222, type=socket.SOCK_STREAM)
finally:
    signal.alarm(0)

print("DNS OK:", sorted({item[4][0] for item in addresses}))
with socket.create_connection(("nats", 4222), timeout=5) as connection:
    print("TCP OK:", connection.getpeername())
PY
```

结果解释：

- `DNS lookup timed out` 或 `Name or service not known`：Docker DNS 或网络别名问题。
- `Connection refused`：域名已解析，但 NATS 没有监听 4222，常见于启动失败或重启。
- `timed out`：连接被丢弃、网络异常，或容器实际不可达。
- 同时出现 `DNS OK` 和 `TCP OK`：网络层正常，继续检查 TLS。

日志中的堆栈如果停在 `getaddrinfo()`，应优先完成本节和第 4 节。

## 6. 验证 TLS 证书和握手

先确认 Server 容器能读取 CA 文件：

```bash
docker compose exec -T server sh -c \
  'ls -l /etc/nats/certs/ca.crt && openssl x509 -in /etc/nats/certs/ca.crt -noout -subject -issuer -dates -fingerprint -sha256'
```

验证 TLS 握手，`server_hostname="nats"` 会同时校验证书 SAN：

```bash
docker compose exec -T server python - <<'PY'
import socket
import ssl

context = ssl.create_default_context(cafile="/etc/nats/certs/ca.crt")
with socket.create_connection(("nats", 4222), timeout=5) as raw_socket:
    with context.wrap_socket(raw_socket, server_hostname="nats") as tls_socket:
        print("TLS OK:", tls_socket.version(), tls_socket.cipher()[0])
        certificate = tls_socket.getpeercert()
        print("Certificate subject:", certificate.get("subject"))
        print("Certificate SAN:", certificate.get("subjectAltName"))
PY
```

常见错误与含义：

| 错误 | 含义 |
|---|---|
| `CERTIFICATE_VERIFY_FAILED` | Server 使用的 CA 无法验证 NATS 服务端证书 |
| `Hostname mismatch` | 服务端证书 SAN 不包含 `DNS:nats` |
| `certificate has expired` | CA 或服务端证书已过期 |
| `WRONG_VERSION_NUMBER` | 客户端使用 TLS，但 4222 端口提供的是明文 NATS |
| `Connection reset by peer` | NATS TLS 配置、客户端证书要求或服务端状态异常 |

确认 Server 与 NATS 容器看到的是同一份 CA：

```bash
docker compose exec -T server sha256sum /etc/nats/certs/ca.crt
docker compose exec -T nats sha256sum /etc/nats/certs/ca.crt
```

两条输出的 SHA-256 必须一致。不要输出或比较 `ca.key`、`server.key` 等私钥。

## 7. 检查 NATS 配置与监听端口

只检查配置语法，不重载服务：

```bash
docker compose exec -T nats nats-server -t -c /etc/nats/nats.conf
```

检查容器内的 4222 监听状态：

```bash
docker compose exec -T nats sh -c \
  'if command -v ss >/dev/null 2>&1; then ss -lnt; else netstat -lnt; fi'
```

需要确认：

- NATS 监听 `0.0.0.0:4222` 或 `[::]:4222`，而非只监听回环地址。
- `nats.conf` 启用了 TLS，且证书路径与 Compose volume 挂载一致。
- `jetstream` 已启用，`store_dir` 可写，启动日志没有存储错误。

## 8. 区分认证和 JetStream 故障

认证或权限错误发生在 DNS、TCP 和 TLS 均成功之后。典型日志会包含：

```text
Authorization Violation
Permissions Violation
JetStream not enabled
Object Store ... not found
```

如果现场日志仍然只是 `TimeoutError`，不要优先修改用户名、密码或 JetStream
权限。先完成网络和 TLS 检查。

核对配置时只确认变量是否存在，不输出变量值：

```bash
docker compose exec -T server python - <<'PY'
import os

for name in ("NATS_SERVERS", "NATS_TLS_ENABLED", "NATS_TLS_CA_FILE"):
    print(f"{name}: {'SET' if os.getenv(name) else 'MISSING'}")
PY
```

## 9. 恢复与验证

### 9.1 恢复 NATS

修正已经确认的配置、证书挂载或网络问题后，重新创建相关容器：

```bash
docker compose up -d nats
docker compose ps nats
docker compose logs --since=5m --tail=200 nats
```

若修改了 Server 的网络、CA 挂载或 NATS 环境变量，再重新创建 Server：

```bash
docker compose up -d server
docker compose ps server
```

重新执行第 5、6 节，必须依次得到 `DNS OK`、`TCP OK`、`TLS OK`。

### 9.2 重新执行包初始化

使用部署脚本中原有的版本号和文件路径重新执行失败命令。不要凭空修改版本号，
也不要默认添加 `--force-upload`。

示例：

```bash
docker compose exec -T server \
  python manage.py controller_package_init \
  --pk_version '<原版本号>' \
  --file_path '<原文件路径>'
```

成功日志应包含：

```text
Connected to NATS and initialized object store
Added entry ...
controller 文件初始化完成！
```

随后检查 Server 和 NATS 最近日志，确认没有新的连接、TLS、认证或 JetStream
错误。若要重跑所有内置包初始化，优先使用当前部署包自带的初始化段，保留原始
参数，不要复制其他版本文档中的文件名。

## 10. 禁止作为修复的操作

- 不要用更长的 `NATS_CONNECT_TIMEOUT` 代替健康检查。
- 不要在部署脚本中增加更长的固定 `sleep`。
- 不要用无限重试等待 NATS。
- 不要忽略 JetStream 初始化命令的失败状态后继续上传包。
- 不要删除 NATS volume 或对象存储数据来“尝试恢复”。
- 不要在 Server 启动期的 `batch_init` 中增加依赖 NATS Object Store 的包上传。

部署脚本应在上传内置包前，使用有界重试验证 NATS DNS、TCP、TLS、认证和
JetStream 均已就绪；失败时保留明确错误并停止该初始化步骤。Server 启动阶段的
依赖边界见 [Server 启动顺序与服务依赖边界](server-startup-dependencies.md)。

## 11. 现场信息回传模板

请回传以下脱敏信息：

```text
故障时间：
部署版本 / 镜像 tag：
docker compose 版本：
宿主机系统：

1. docker compose ps -a nats server：
2. NATS restart / exit 状态：
3. NATS 最近 200 行日志（删除用户名、地址、证书内容）：
4. Server 与 NATS 的网络名称：
5. DNS 检查：成功 / 失败，错误文本：
6. TCP 检查：成功 / 失败，错误文本：
7. TLS 检查：成功 / 失败，错误文本：
8. 两端 CA SHA-256 是否一致：是 / 否：
9. nats-server 配置语法检查：成功 / 失败：
10. 原始初始化命令及完整异常尾部（凭据脱敏）：
```

不要回传 `.env`、连接 URL 中的凭据、Token、私钥或证书正文。
