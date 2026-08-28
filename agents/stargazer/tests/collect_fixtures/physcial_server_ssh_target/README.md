# QA：物理服务器 SSH 采集目标（幂等 nic 两次采集）

本目录**不是**一套并行 BK-Lite 产品栈。产品进程仍用现场已有 compose；这里只补一个可 SSH 的物理服务器替身，接线方式对齐 `agents/stargazer/tests/collect_fixtures`（ubuntu:22.04、root / `testpw`、宿主机端口映射）。

discover 脚本 `physcial_server_default_discover.sh` 只扫 PCI 网卡（`lspci` + `/sys/bus/pci/devices/.../net`）。容器默认 privileged，以便看到宿主机 virtio/PCI 网卡；若 PCI 下没有任何 net iface，entrypoint 会种一张 MAC=`0a:00:00:00:00:01` 的 QA 网卡，避免「两次采集 nic 数都是 0」的空断言。

## 1. 拉起 BK-Lite 产品栈（已有 compose，不要另起一套）

现场路径：

| 形态 | 目录 |
|------|------|
| 单机 | `/opt/bk-lite/deploy/docker-compose` |
| HA | `/opt/bk-lite/deploy/docker-compose-ha` |

```bash
cd /opt/bk-lite/deploy/docker-compose    # HA 则改 docker-compose-ha
docker compose ps
# 需要的是已在跑的 server + 执行 SSH JOB 的采集节点（stargazer / node）
```

渲染与启动以该目录现有 `docker-compose.yaml` / `bootstrap.sh` 为准，见 `docs/openapi-gateway/onboarding.md`。本仓库不包含那份产品 compose，不要复制一份平行栈。

## 2. 拉起 SSH 采集目标

在**本仓库**执行（可与产品栈并行）：

```bash
cd agents/stargazer/tests/collect_fixtures/physcial_server_ssh_target
docker compose up -d --build
docker compose ps
# sshd 在镜像内已装好；容器起来后几乎立刻可连 12226
```

sshd / pciutils 在 **镜像构建** 时安装（compose `build.network: host`，避免 Docker bridge 访问 Ubuntu 源超时）。entrypoint 只配账户并种 QA 网卡。

若 `docker.m.daocloud.io/library/ubuntu:22.04` 拉不到，把 `Dockerfile` 的 `FROM` 改成 `ubuntu:22.04` 再 `up -d --build`。

无 systemd 的嵌套 overlay 环境若 `overlayfs: invalid argument`，把 Docker 存储驱动改成 `vfs` 后再 `up`（daemon.json 的 `storage-driver`，不是另起产品栈）。

### 让采集节点用容器名访问（推荐）

把目标接到产品栈的 docker 网络，JOB 里填主机名即可：

```bash
# 查产品栈网络名（常见 *default / *bk-lite*）
docker network ls
docker network connect <bklite_network> physcial-server-ssh-target
```

此时采集节点 SSH：

| 项 | 值 |
|----|----|
| 服务/容器 | `physcial-server-ssh-target` |
| 主机（instances.ip_addr） | `physcial-server-ssh-target` |
| 端口 | `22` |
| 用户 | `root` |
| 密码 | `testpw` |

### 采集节点跑在宿主机，或不方便连同一网络

| 项 | 值 |
|----|----|
| 主机 | `127.0.0.1`（或宿主机 IP） |
| 端口 | `12226` |
| 用户 | `root` |
| 密码 | `testpw` |

采集节点若在另一个容器里，把主机改成 `host.docker.internal` 或 docker bridge 网关，端口仍是 `12226`。

冒烟：

```bash
sshpass -p testpw ssh -o StrictHostKeyChecking=no -p 12226 root@127.0.0.1 'echo ok'
# 或（同一 compose 网络内）
sshpass -p testpw ssh -o StrictHostKeyChecking=no -p 22 root@physcial-server-ssh-target 'echo ok'
```

## 3. 在 CMDB 里建 SSH JOB，指向该容器

1. 采集对象选 **物理服务器 SSH**（树节点 id / `model_id` = `physcial_server`，driver = `job`，`task_type=HOST`）。不要选「物理服务器 IPMI」。
2. 实例：`ip_addr` = 上一节主机名或 IP。
3. 凭据：协议 SSH；账户 `root`；密码 `testpw`；端口 `22` 或 `12226`（与上一节一致）。
4. 接入点选能访问该 SSH 目标的采集节点。

## 4. 采集两次，核对 nic 数量与 contains 方向

```bash
# 目标侧先确认脚本能扫到可入库网卡（非 lo、非空 MAC）
sshpass -p testpw ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 12226 root@127.0.0.1 \
  'echo ok; PATH=/usr/local/sbin:$PATH lspci | grep -iE "ethernet|network" || true; cat /sys/class/net/ethqa/address 2>/dev/null || true'
```

无完整 BK-Lite 产品栈时，用本目录脚本对 **live SSH 输出** 跑两次 HostCollect / Management 入库路径（sqlite 即可）：

```bash
cd server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run python ../agents/stargazer/tests/collect_fixtures/physcial_server_ssh_target/run_twice_collect.py
```

在 CMDB 对该 `physcial_server` 实例执行采集 **一次**，记下：

- `nic` 实例数（按 `inst_name` = 规范化 MAC）
- contains 边：`model_asst_id=physcial_server_contains_nic`，**src = physcial_server 实例，dst = nic 实例**

再执行 **第二次** 采集：

- `nic` 实例数必须与第一次相同
- 不得出现 src=nic、dst=physcial_server 的 contains 边

## 5. 停掉目标（产品栈保持不动）

```bash
cd agents/stargazer/tests/collect_fixtures/physcial_server_ssh_target
docker compose down
```
