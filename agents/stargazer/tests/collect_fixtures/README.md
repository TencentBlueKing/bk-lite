# CMDB 数据库/中间件采集执行层真实环境 Mock 数据采集工具

## 目的

对每个可容器化的数据库/中间件,在本机拉起 Docker 容器,跑一次真实采集,把原始 stdout 落盘为 `tests/fixtures/collect/<model>.json`,作为后续端到端 e2e 测试的 Mock 数据。

**不**做端到端链路(NATS 推送 / CMDB 入库 / Celery 调度本次不考虑)。

## 入口类型

工具支持 3 种入口形态,按 spec.entry_type 区分:

| entry_type | 数据流 | 适用对象 |
|-----------|--------|---------|
| `python` | 从 host 直接调 SDK(pymysql/psycopg2)连服务镜像 | mysql / postgresql |
| `shell`  | `docker exec` 在服务镜像内跑 `*_default_discover.sh` | redis(镜像自带 redis-cli) |
| `ssh`    | 启动 ubuntu:22.04 VM,apt install 服务,SSH 进 VM 跑采集脚本 | mongodb / nginx / tomcat / rabbitmq |

> **背景**：shell collector (`*_default_discover.sh`) 设计为“在目标主机本地嗅探”——看 `ps`、读 `/proc`、调用 `redis-cli` / `jps` 等 CLI；官方服务镜像通常缺少这些工具，SSH fixture 通过 ubuntu:22.04 安装依赖解决。历史设计的迁移目标见 `docs/agents/spec-migration-map.md`。

## 当前支持的对象

| model_id | 入口类型 | image | 备注 |
|----------|---------|-------|------|
| `mysql` | python | `docker.m.daocloud.io/mysql:8.0` | 用 pymysql 远程连库 |
| `postgresql` | python | `docker.m.daocloud.io/library/postgres:16-alpine` | 用 psycopg2 远程连库 |
| `redis` | shell | `docker.m.daocloud.io/library/redis:7-alpine` | 镜像自带 redis-cli,docker exec 即可 |
| `mongodb` | ssh | `docker.m.daocloud.io/library/ubuntu:22.04` | ubuntu + apt install mongodb-org |
| `nginx` | ssh | `docker.m.daocloud.io/library/ubuntu:22.04` | ubuntu + apt install nginx |
| `tomcat` | ssh | `docker.m.daocloud.io/library/ubuntu:22.04` | ubuntu + apt install tomcat9 |
| `rabbitmq` | ssh | `docker.m.daocloud.io/library/ubuntu:22.04` | ubuntu + apt install rabbitmq-server |

> **3 个对象当前不在 catalog 中**(daocloud 镜像源未镜像 + 复杂度):`elasticsearch` / `kafka` / `activemq`。

## 用法

### 环境前置

macOS orbstack 用户需设置:
```bash
export DOCKER_HOST=unix:///Users/<you>/.orbstack/run/docker.sock
```

### 列出所有可用对象

```bash
cd agents/stargazer
.venv/bin/python -m tests.collect_fixtures.cli --list
```

### 采集单个对象

```bash
.venv/bin/python -m tests.collect_fixtures.cli nginx
```

ssh 入口输出(预计 30-120 秒,主要在 apt install):
```
==> [nginx] 启动容器 (docker.m.daocloud.io/library/ubuntu:22.04)
    container_id = abc123
==> [nginx] bootstrap sshd (docker exec)
==> [nginx] 等待 SSH 就绪
==> [nginx] 安装服务
==> [nginx] 启动服务
==> [nginx] 等待服务就绪
==> [nginx] 调 collector
==> [nginx] 落盘
    ✅ .../fixtures/collect/nginx.json
==> [nginx] 销毁容器
```

python 入口输出(更快,~10s):
```
==> [mysql] 启动容器 (mysql:8.0)
    container_id = abc123
==> [mysql] 等待端口就绪
==> [mysql] 执行 init 脚本
==> [mysql] 调 collector
==> [mysql] 落盘
    ✅ .../fixtures/collect/mysql.json
==> [mysql] 销毁容器
```

### 批量采集全部对象

```bash
.venv/bin/python -m tests.collect_fixtures.cli --all
```

### Debug:不销毁容器

```bash
.venv/bin/python -m tests.collect_fixtures.cli nginx --keep-container
```

## 产物

`tests/fixtures/collect/<model_id>.json`:

```json
{
  "model_id": "nginx",
  "captured_at": "2026-07-05T...",
  "image": "docker.m.daocloud.io/library/ubuntu:22.04",
  "container_meta": { "container_id": "...", "image": "..." },
  "params": { "host": "127.0.0.1", "ssh_port": 12222, "password": "***" },
  "raw_stdout": { /* collector stdout parse 后的 dict,8-13 个 keys */ }
}
```

> 敏感字段(`password` / `secret` / `token` / `passwd`,忽略大小写)已自动掩码为 `"***"`。

## SSH 入口的流水线细节

`entry_type=="ssh"` 时 cli 按以下顺序执行:

1. `start_container(spec)` — 起 `docker.m.daocloud.io/library/ubuntu:22.04` 容器,跑 `while true; do sleep 3600; done` 保持容器存活
2. `bootstrap_sshd_in_container(handle)` — `docker exec_run` 在容器内装 sshd + 配置 + 启动(走 `apt-get install openssh-server`,不走 SSH,绕开 chicken-and-egg)
3. `wait_ssh_ready(handle, spec)` — 轮询 SSH 端口直到 paramiko 连上
4. `install_services(handle, spec)` — SSH 进 VM 跑 `spec.install_commands`(装业务服务如 nginx/mongodb)
5. `start_services(handle, spec)` — SSH 跑 `spec.start_commands`(启动业务守护进程)
6. `wait_service_ready(handle, spec)` — 轮询 `spec.ready_check.command` 直到 exit 0(端口已监听)
7. `collect_once(spec, handle)` — SSH 上传 `init/<model>_default_discover.sh` 到 `/tmp/`(base64+heredoc),执行,捕获 stdout
8. `dump(spec, raw)` — 原子写 `tests/fixtures/collect/<model>.json`(敏感字段掩码)
9. `remove(handle)` — 销毁容器

## 字段说明(Spec dataclass)

- `image`: Docker 镜像(可用 daocloud 前缀 `docker.m.daocloud.io/`)
- `ports`: docker SDK 约定 `{container_port: host_port}`(如 `{22: 12222}`)
- `env`: 容器环境变量
- `wait_strategy`: `{"type": "tcp"|"ssh", "port": 端口, "timeout": 秒, "interval": 秒}`
- `init_script`: 在采集前执行的 SQL/sh 路径(相对 `init/`);**ssh 入口必填**,指向 `*_default_discover.sh`
- `entry_type`: `"python"` | `"shell"` | `"ssh"`
- `entry_module` / `entry_class`: python 入口必填(如 `plugins.inputs.mysql.mysql_info.MysqlInfo`)
- `entry_method`: 默认 `list_all_resources`
- `collector_kwargs`: 传给 collector 的参数
- `vm_privileged`: 是否 privileged 模式(ssh 入口一般 False)
- `vm_ssh_user` / `vm_ssh_password`: ssh 入口必填
- `install_commands`: SSH 顺序执行的安装命令(tuple)
- `start_commands`: SSH 顺序执行的启动命令(tuple,业务服务)
- `ready_check`: `{"command": "ss -tln | grep -q :PORT", "timeout": 60, "interval": 1.0}`

## 测试

```bash
cd agents/stargazer
.venv/bin/python -m pytest tests/collect_fixtures/ -v
```

45 个单测,覆盖 catalog / dump / docker_lifecycle / run_collector / cli / vm_ssh。

## 已知限制

1. **3 个对象不在 catalog**:`elasticsearch` / `kafka` / `activemq`(daocloud 镜像源未镜像 + 复杂度)。需要时手动补可访问镜像源
2. **macOS orbstack DOCKER_HOST**:必须设置
   ```bash
   export DOCKER_HOST=unix:///Users/<you>/.orbstack/run/docker.sock
   ```
3. **tomcat9 路径特殊**:ubuntu 22.04 jammy 包把 `server.xml` 放在 `/etc/tomcat9/`,不是 `/usr/share/tomcat9/conf/`。catalog 的 install_commands 里 `cp -r /etc/tomcat9/. /usr/share/tomcat9/conf/` 已处理
4. **每个 ssh 对象独立 SSH 端口**(避免 catalog validate 端口冲突):nginx=12222, mongodb=12223, rabbitmq=12224, tomcat=12225
5. **每个对象首次安装耗时**:ubuntu + apt install 大约 30-120 秒
