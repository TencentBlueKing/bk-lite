# 发行镜像安全补丁与验收

## 海外漏扫报告：OpenSSL、Log4j 与系统 Python 工具

Fusion 执行器 OpenSSL 1.1.1k 的升级构建由 PR #6862 提供（固定 OpenSSL 3.5.9），
需要重新构建并分发完整执行器制品。镜像构建不再调用额外的执行器校验参数；
仅更新宿主机 OpenSSL 或 Fusion 的 Ubuntu 系统包不能替换 `_internal` 中的库。

报告中的 Conductor 3.32.1 携带 Log4j 2.25.4，Elasticsearch 7.17.21 携带 2.17.1。
使用 `Dockerfile.conductor` / `Dockerfile.elasticsearch` 构建独立补丁镜像；不跨产品主版本升级。
Log4j API、Core 和 Conductor 中检测到的适配模块统一更新到 2.25.5，
制品从 Maven Central 官方路径获取，并核对入库的 SHA256 及 JAR 内 Maven 坐标。
Elasticsearch 的定制 Core 继续删除 `JndiLookup.class`，不恢复原有已移除的危险类。
Conductor 同步更新 classpath/layers 索引，保留 Spring Boot 的嵌套 JAR 存储格式；
拒绝未核对的依赖版本、未知模块、重复模块或带真实外层签名的 JAR。

```sh
# 先记录当前上游镜像摘要；以下变量由发布人员填写。
BASE_IMAGE='当前产品镜像@sha256:实际摘要'
CANDIDATE_IMAGE='独立候选镜像:本次安全修复标签'
PRODUCT='conductor' # 或 elasticsearch；ES 入口仅适用于已核对的 7.17.21 布局
docker pull "$BASE_IMAGE"
RUNTIME_USER=$(docker image inspect --format '{{.Config.User}}' "$BASE_IMAGE")
docker build --pull --no-cache --platform linux/amd64 \
  --build-arg BASE_IMAGE="$BASE_IMAGE" --build-arg RUNTIME_USER="${RUNTIME_USER:-0}" \
  -f "deploy/security/Dockerfile.$PRODUCT" -t "$CANDIDATE_IMAGE" deploy/security
```

`Dockerfile.system` 还会检查 Ubuntu 24.04 中已经安装的 `python3-pip`、`python3-pip-whl`、
`python-wheel-common`、`python3-wheel`、`python3-wheel-whl`，只升级已安装的包：

| 包族 | 最低发行版补丁版本 |
|---|---|
| pip / pip-whl | `24.0+dfsg-1ubuntu1.3+esm1` |
| wheel / wheel-whl / wheel-common | `0.42.0-2ubuntu0.1~esm1` |

如果构建软件源未提供 USN-8344-1 / USN-8221-1 的修复，门禁失败。
需要时通过构建环境配置 Ubuntu Pro ESM；禁止将订阅凭据写入 Dockerfile、镜像层或仓库。
此入口仅修复派生镜像；报告若命中宿主机的 dpkg 包，仍需在宿主机维护流程中安装同样的发行版补丁。
用 `pip install -U pip` 替换 Python 环境不能证明上述 dpkg 系统包已更新。

发布前需验证 Conductor 的元数据写入、工作流执行与读取，以及 Elasticsearch 索引写入、检索和重启恢复。
报告中的 containerd 历史快照和 `/var/tmp/itsm-es-log4j-backup-*` 必须按运行引用单独核对，
不能把备份路径或未使用镜像层直接当成运行服务，也不能直接删除 snapshot 目录。
这些构建入口不自动修改 Jenkins、第三方部署模板或存量运行容器。

依据：[Apache Log4j](https://logging.apache.org/security.html)、
[pip USN-8344-1](https://ubuntu.com/security/notices/USN-8344-1)、
[wheel USN-8221-1](https://ubuntu.com/security/notices/USN-8221-1)。

## Brotli 修改范围（CVE-2026-111497）

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

## 补齐 Pillow 内置库与存量镜像

系统 `libbrotli1` 修复不覆盖 Pillow 预编译 wheel 自带的 `pillow.libs`。
Server 的发行构建现在会保留 `pyproject.toml` 中的 Pillow 版本，从源码重新安装，
链接发行版 FreeType / Brotli；不再使用 PyPI wheel 内置的 Brotli。
该步骤仅发生在镜像构建期，不增加启动检查、校验器或 Jenkins 门禁。
安装图像、字体和排版的编译依赖，以保留 JPEG、PNG、TIFF、WebP、JPEG 2000、
AVIF 和 Raqm 字体排版能力。当前入口面向 Debian 13 / Python 3.12 镜像。
构建需要可访问 Debian 和 Python 软件源；离线客户接收构建好的镜像，不能在客户容器中联网安装。

| 服务 | 本次补齐 / 使用方式 |
|---|---|
| Server | 原有发行 Dockerfile 自动源码重建 Pillow，需重新出包、替换容器 |
| MLflow | 新增 `Dockerfile.mlflow`，同时更新系统 Brotli、源码重建当前 Pillow |
| Conductor | 原有 `Dockerfile.conductor` 同时更新系统 Brotli 和 Log4j |
| Webhookd | 原有 `agents/webhookd/Dockerfile` 已更新系统 Brotli，需重新出包、替换旧容器 |
| FalkorDB | 沿用 `Dockerfile.falkordb`，同时更新原 Node 主版本及系统 Brotli；生产和开发镜像分别构建 |

MLflow 补丁镜像的构建上下文与其他补丁入口不同，使用**仓库根目录**：

```sh
BASE_IMAGE='MLflow 当前镜像@sha256:实际摘要'
CANDIDATE_IMAGE='本地候选镜像:新的修复标签'
docker pull "$BASE_IMAGE"
RUNTIME_USER=$(docker image inspect --format '{{.Config.User}}' "$BASE_IMAGE")
docker build --pull --no-cache \
  --build-arg BASE_IMAGE="$BASE_IMAGE" --build-arg RUNTIME_USER="${RUNTIME_USER:-0}" \
  -f deploy/security/Dockerfile.mlflow -t "$CANDIDATE_IMAGE" .
# 若应用使用独立虚拟环境，另传 --build-arg PYTHON=/实际虚拟环境/bin/python。
docker save -o mlflow-patched.tar "$CANDIDATE_IMAGE"
```

离线环境导入 `docker load -i mlflow-patched.tar`，在原有 Compose 配置中替换对应服务的
镜像标签，再按原配置重建该服务，保留现有卷和环境变量。回滚时切回原镜像标签。
Conductor、Webhookd 和 FalkorDB 同样需要交付各自新镜像；仅更新 Server 不会修复其他容器。

独立产物回归测试（不接入 Jenkins / 发布链路）位于
`deploy/security/tests/integration/test_pillow_runtime.py`。在包含测试文件及
DejaVu Sans 字体的候选镜像内，使用应用实际 Python 执行，例如：

```sh
PILLOW_EXPECTED_VERSION=11.3.0 python3 deploy/security/tests/integration/test_pillow_runtime.py
# MLflow 对应截图环境设 PILLOW_EXPECTED_VERSION=12.1.1。
```

发布前在候选镜像中确认 Pillow 版本保持不变、`_imagingft` 经 FreeType 链接系统
`libbrotlidec.so.1`，且不再引用 `pillow.libs` 中的 Brotli；同时验证图像读写、中文字体绘制、
MLflow 实验与产物读写。检查实际运行进程时应使用同一 Python 环境，重新创建进程后再复核。

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
它通过原镜像已有的 NodeSource 22.x / 24.x 软件源升级 `nodejs` 包，同时更新系统 Brotli，
分别校验 Node 稳定版不低于 22.23.4 / 24.22.1，且实际运行版本必须与 dpkg 包清单一致。
不再仅复制可执行文件，以免运行版本已更新、漏扫清单仍保留旧包。
其他发行版或没有已安装 `nodejs` 包的镜像拒绝构建。
这只是候选构建入口，发布前必须验证 FalkorDB 数据读写及附带 Node 应用。

## 验证与发布

1. 运行 `python3 -m unittest discover -s deploy/security/tests -v`。
   Linux 使用真实 dpkg 比较旧包、二进制重建包和安全回补包；macOS 会跳过这两项。
   其余测试执行 Dockerfile 的实际 RUN 层，验证更新失败、补丁不足、未知发行版会阻止构建，
   并验证 Node 包版本、实际运行版本必须一致，不操作系统包或业务服务。
2. 构建时使用 `--pull --no-cache`。安全更新层需能从对应软件源取得补丁，
   最终发行 Dockerfile 也必须接入同样的更新与版本检查。
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

## Jenkins 与部署补充（待 review 后接入）

`jenkins-brotli.groovy` 是阶段片段：放在应用镜像构建之后、发布之前。
不替换现有流水线，不调用 Jenkins API，也不触发远程部署。按当前工作目录调整
`deploy/security` 前缀；凭据沿用 Jenkins 的 registry credential binding，禁止写入脚本。
候选标签必须为本次发布独有（例如提交 SHA + BUILD_NUMBER），禁止复用 latest。

- 生产、开发 FalkorDB 分别设置 `FALKORDB_BASE_IMAGE`、`DEV_FALKORDB_BASE_IMAGE`
  （实际环境镜像摘要），及两个不同的 `*_CANDIDATE_IMAGE`。脚本分别构建、保留
  USER/ENTRYPOINT/CMD 并检查版本。Debian 12 的 NodeSource 22/24 分支分别升级至
  22.23.4 / 24.22.1 或更高同主版本；缺少软件源、未知系统或跨主版本均失败。
- `LICENSE_IMAGE` 必须由授权服务仓库重建并提供安全镜像摘要。这个门禁检查 Node
  22/24 安全版本，不会把当前 22.23.3 自动变成安全版；未取得镜像时不能宣布全部覆盖。
- `FUSION_IMAGE` 为重新构建的最终发行镜像，检查系统 libbrotli。OpenSSL
  升级仍需通过 #6862 的专用构建入口重新生成执行器，本 Brotli 门禁不代替 OpenSSL 修复。
- Web、Server、Stargazer 沿用原构建阶段，部署清单同时锁定它们的实际修复镜像。
  推送在全部候选门禁通过后接入原凭据流程；推送后读取对应仓库 RepoDigest，禁止
  仅凭本地 image ID 或可变标签填写下方清单。

### 按 Compose 项目生成部署覆盖文件

主平台、授权服务、开发环境若属于不同 Compose 项目，分别建立清单、生成覆盖文件
并独立验收。服务名取实际 `docker compose config --services` 输出，不能使用容器名。
例如主平台 `release.json`（将下列占位值替换为真实完整摘要）：

```json
{"services": {
  "web": {"image": "registry/web@sha256:真实64位摘要", "profile": "node"},
  "server": {"image": "registry/server@sha256:真实64位摘要", "profile": "system"},
  "stargazer": {"image": "registry/stargazer@sha256:真实64位摘要", "profile": "system"},
  "falkordb": {"image": "registry/falkordb@sha256:真实64位摘要", "profile": "node-system"}
}}
```

授权服务清单包含其实际服务名，使用 `node` profile；开发环境 FalkorDB 使用
`node-system` profile。Fusion 若是独立采集器交付，单独交付安全镜像，不能假设
主平台 Compose 更新会替换已下发的采集器。清单须人工核对所有受影响服务；工具
仅检查清单中的条目，不做跨项目资产发现。

构建节点/部署节点预先拉取各摘要镜像，运行以下操作；工具不负责推送、拉取或更新容器：

```sh
# 每次使用新目录；已存在的覆盖文件拒绝覆盖。候选检查不执行应用启动入口。
python3 deploy/security/brotli_release.py prepare \
  --manifest release.json --output compose.security.json
# 与现有部署保持相同 -p、-f 顺序、env-file、profile 和工作目录；下列为单基础文件示例。
# 人工 review 覆盖文件，确认维护窗口和备份后，才在部署节点执行：
docker compose -p compose -f docker-compose.yaml -f compose.security.json \
  up -d --no-build --pull never web server stargazer falkordb
# 验证所有副本的实际 image ID、运行状态和版本，不以镜像标签代替容器核验。
python3 deploy/security/brotli_release.py verify --manifest release.json --project compose \
  -f docker-compose.yaml -f compose.security.json
```

`bootstrap.sh` 可能重新生成配置或执行另一条 compose 命令；必须在其最终 `up` 调用
加入同一覆盖文件，或在 bootstrap 完成后执行上述受控替换。不能只构建/推送镜像
便宣称环境已修复。开发、授权项目必须分别执行，采集器走其实际更新链路。
`verify` 支持重复的 `--env-file`、`--profile` 参数，按原部署参数传入。
版本门禁之后仍需完成平台登录、授权校验、FalkorDB 读写及采集任务冒烟。

回滚前保存上一版各项目的镜像摘要清单和数据备份；保留原卷、不执行 `down -v`、
不删 containerd snapshot。失败时以同样 compose 文件顺序换回上一版镜像覆盖文件
并重建受影响服务，再验收业务；回退旧镜像意味着漏洞重新存在，须记录并重新修复。
