# CVE-2026-111497：Brotli 镜像修复与验收

## 修改范围

本次修改在构建期更新系统 `libbrotli1`，并使用发行版完整包版本校验补丁。
软件源无法提供安全版本、包更新失败或发行版不在已验证范围时，构建失败；
不在容器启动时执行更新，不修改配置、业务数据或启动顺序。

- Server 基础镜像及最终镜像、Stargazer、Webhookd、Fusion Collector、Telegraf：
  在各自原有构建入口执行系统包更新和版本门禁。
- Python 基础镜像显式采用 `python:3.12-trixie`，避免浮动发行版使补丁基线失效。
- Web 已在主干使用 `node:24.22.1-alpine`，本 PR 不重复改动；旧运行容器仍需重新发布。
- 第三方镜像没有位于本仓库的应用构建源码，使用下述派生镜像入口，
  交付流水线及部署清单必须切换到派生镜像的新版本后才算完成修复。
- Fusion 执行器内置 OpenSSL 由 PR #6862 单独处理；系统 Brotli 更新不能替代该修复。

## 补丁基线

| 发行版 | libbrotli1 最低完整版本 |
|---|---|
| Debian 12 | `1.0.9-2+deb12u1` |
| Debian 13 | `1.1.0-2+deb13u1` |
| Ubuntu 20.04 | `1.0.7-6ubuntu0.1+esm1` |
| Ubuntu 22.04 | `1.0.9-2ubuntu0.1` |
| Ubuntu 24.04 | `1.1.0-2ubuntu0.1` |

Debian 的 `+b6` / `+b7` 是二进制重建版本，不能替代安全更新后缀。
Ubuntu 20.04 的补丁需要可用的 ESM 软件源；未提供时门禁会失败，不允许绕过。
Alpine 3.20 的旧 Kafka 镜像、Oracle Linux MySQL 镜像以及无 shell 的镜像不适用此 apt 入口，
须另选发行商确认包含修复的镜像，不能凭上游版本号认定已修复。

依据：
[Debian](https://security-tracker.debian.org/tracker/CVE-2026-111497)、
[Ubuntu](https://ubuntu.com/security/CVE-2026-111497)、
[Node.js 24.22.1](https://nodejs.org/en/blog/release/v24.22.1)、
[Alpine](https://security.alpinelinux.org/vuln/CVE-2026-111497)。

## 第三方应用镜像

以下命令仅生成独立候选镜像，不推送、不替换运行容器。先拉取并记录上游镜像摘要。
`BASE_IMAGE`、`CANDIDATE_IMAGE` 必须替换为实际镜像引用，候选标签不得覆盖现有标签。

```sh
BASE_IMAGE='上游镜像@sha256:实际摘要'
CANDIDATE_IMAGE='本地候选镜像:新版本'
docker pull "$BASE_IMAGE"
RUNTIME_USER=$(docker image inspect --format '{{.Config.User}}' "$BASE_IMAGE")
RUNTIME_USER=${RUNTIME_USER:-0}

docker build --pull --no-cache --platform linux/amd64 \
  --build-arg BASE_IMAGE="$BASE_IMAGE" \
  --build-arg RUNTIME_USER="$RUNTIME_USER" \
  -f deploy/security/Dockerfile.system \
  -t "$CANDIDATE_IMAGE" deploy/security
```

用于 Debian / Ubuntu 的 Conductor、MLflow、ITSM、Elasticsearch 等镜像。
上游 `USER` 必须按上述方式恢复；Dockerfile 不提供默认用户，避免将原非 root 应用变成 root。
保留上游 ENTRYPOINT、CMD、端口、卷和工作目录。

FalkorDB 检测到的 Node.js 24.14.0 不会因更新 libbrotli 而自动修复。对 Debian 12
派生镜像使用同样命令，但将 Dockerfile 改为 `deploy/security/Dockerfile.falkordb`。
它从官方 Node.js 24.22.1 Bookworm 镜像复制同架构可执行文件，替换原 Node 的真实路径，
校验 `node --version`，同时更新系统 Brotli。其他发行版拒绝构建。
这只是候选构建入口，发布前必须验证 FalkorDB 数据读写及附带 Node 应用。

## 验证与发布

1. 运行 `python3 -m unittest discover -s deploy/security/tests -v`。
   Linux 使用真实 dpkg 比较旧包、二进制重建包和安全回补包；macOS 会跳过这两项。
   其余测试执行 Dockerfile 的实际 RUN 层，验证更新失败、补丁不足、未知发行版会阻止构建，
   并在临时目录验证 Node 符号链接目标替换，不操作系统包或业务服务。
2. 构建时使用 `--pull --no-cache`。安全更新层需能从对应软件源取得补丁，
   企业覆盖的最终 Dockerfile 也必须接入同样的更新与版本检查。
3. 独立候选容器使用 `--network none --read-only --cap-drop ALL --security-opt no-new-privileges`
   和 CPU、内存、进程数限制；分别核对系统包、Node 和 curl 的链接库。
   不运行漏洞利用输入，不以“curl 不存在”推断无 Brotli。
4. 在测试环境验证 Web 登录和代理请求、Server API / Worker、Stargazer 采集、
   Fusion 任务与采集恢复、Conductor 工作流、MLflow 读写及 FalkorDB 读写。
   这些业务验收不能由版本门禁替代。
5. 记录旧镜像摘要、持久化卷及回滚方式，按服务逐批发布。不得清空数据卷或手工删除
   containerd 快照。复核所有运行实例的镜像 ID、包版本、Node 版本并复扫后收口。

宿主机与容器的软件包独立维护。Debian 12 宿主机的更新应作为独立运维变更，
先模拟更新、检查依赖和可用补丁，再在维护窗口更新 `libbrotli1`。
本 PR 不执行宿主机更新、服务重启、镜像推送或部署，也不代表存量环境已经完成修复。
