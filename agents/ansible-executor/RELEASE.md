# Fusion 执行器发行构建：OpenSSL 3.5.9

此入口面向 Linux amd64、GLIBC 2.28 基线。它构建独立制品，不安装、不部署、不推送镜像。

## 构建

在独立 Linux 构建目录使用 Python 3.12.15（其 `ssl` 必须实际为 OpenSSL 3.5.9）、uv、C 编译器、make、Perl、Rust/Cargo 和 readelf。推荐复用已验证的 uv 0.13.3、Rust 1.90.0 工具链；以最终包的实际版本和 GLIBC 校验为准。构建机限制 2 CPU / 3 GiB，保留构建日志。

```bash
make package \
  RELEASE_PYTHON=/path/to/python3.12 \
  WORK_DIR=/path/to/new-build-directory \
  DIST_DIR=/path/to/new-dist-directory
```

`WORK_DIR` 必须尚不存在且位于源码目录外；输出中的 `ansible-executor` 必须尚不存在。失败不会覆盖已有输出。构建期间不使用源码目录的 `.venv`。

构建脚本按照 `release-sources.json` 下载和核对 OpenSSL / cryptography 官方源码哈希。OpenSSL 使用 `no-shared no-module` 编译为私有静态库，将 legacy provider 一并编入 libcrypto，再用 `OPENSSL_DIR` / `OPENSSL_STATIC=1` 重编译 cryptography wheel。`uv sync` 后安装该 wheel，随后直接调用虚拟环境中的 PyInstaller，避免再次 `uv run` 将 wheel 恢复为默认发行版。

离线源码可通过 `build_release.py --sources-dir /path/to/archives` 提供；目录必须包含锁文件中的两个源码归档，仍执行 SHA-256 检查。Python 依赖、Rust crates 和 Ansible collection 也必须具备独立可用的下载源/缓存；该参数并不代表完整离线构建。

## 强制检查

`ansible-executor.spec` 自身检查构建 Python/OpenSSL 和 cryptography/OpenSSL，因而直接调用 PyInstaller 也不能绕过版本要求。构建后运行最终冻结程序，检查实际双 OpenSSL 版本、所有 ELF 的 GLIBC 需求以及旧 OpenSSL 文件/依赖，生成 `_internal/release-manifest.json`。最后屏蔽外部 provider 目录和 OpenSSL 配置，执行 NTLM/RC4 标准向量及完整性检查，避免构建机的 `legacy.so` 掩盖可移植性问题。

新产物提供两个无业务副作用的诊断入口：

```bash
./ansible-executor --build-info
./ansible-executor --verify-release
```

前者输出冻结运行时版本；后者还核对组件文件清单、哈希和 NTLM/RC4 标准向量，并拒绝旧 `.so.1.1` / hmac 残留。这两个入口在加载业务配置或连接 NATS 前退出。普通启动路径不主动执行发行检查。

本仓库的 Fusion Dockerfile 在 ADD 后执行 `--verify-release`。本 PR 的范围是执行器构建、制品校验及该镜像构建检查。

单机、HA 及 wxc 内嵌安装脚本属于 `WeOps-Lab/bklite-website` 仓库，其导出前校验及安装导出回归测试是后续待接入的配套工作，不包含在本 PR 中。本 PR 不提供安装包导出阶段的校验保证。后续接入时，新安装脚本应与具备 `--verify-release` 入口的新镜像配套，不能搭配旧镜像发布。

存量宿主 `bin` 的备份、停机、替换和回退属于另一个升级任务，本改动不改变其操作流程。

## Jenkins 接入（尚未应用到在线 Job）

`support-files/jenkins-build-release.sh` 是两条 Job 的共用入口。只读读取配置后生成的 `support-files/jenkins-openssl359.patch` 提供 `fusion-collectors` / `WeOpsx` 两个构建函数的替换片段；它不是可直接提交给 Jenkins 的完整 config.xml。应用时按对应 Job 的 shell / Groovy script 片段替换并验证配置，不能将 patch 文件直接上传为 Job 配置。

需要构建节点参数：

- `FUSION_RELEASE_PYTHON`：实际满足要求的 Python 可执行文件。
- `FUSION_RELEASE_UV`：可选，默认 `uv`。
- `FUSION_RELEASE_SOURCES`：可选，已下载的官方源码目录。
- `DIST` / `WORKSPACE`：沿用 Job 路径。输出为 `$DIST/linux/ansible-executor/`，并生成同一产物的 `ansible-executor-amd64/` 副本，覆盖两种 Docker context 布局；任一旧输出存在即拒绝覆盖。

企业 Job 会覆盖 Fusion Dockerfile，需给最终生效的企业 Dockerfile 同样添加 `--verify-release` 构建检查。本地仅修改了开源 Dockerfile；企业源码并不在当前 checkout 中。

若企业最终 Dockerfile 使用 `ansible-executor-amd64` / `ansible-executor-arm64` 目录，共用入口已生成对应 amd64 目录；不能沿用旧 DIST 中的 arm64 产物继续发布。ARM64 不在本次已验证范围，需另行构建验证后才可启用对应发布分支。

本次不调整线上 Job、不运行带 push 的流水线、不发布镜像、不更新包存储、不更换任何运行目录。正式发布时还需新版本、最终企业构建上下文和离线介质清单配套；现有仅含 server/web 的增量包不能承载 Fusion。

## 验证

- 单元测试：`python -m pytest tests -q --cov=release_policy --cov=build_release`。
- 后续部署集成验收：待 bklite-website 配套改动接入后，在该仓库执行安装导出回归测试；不作为本 PR 已提供的测试。
- Linux 必须执行本文件的真实构建，验证最终程序 `--verify-release`、新镜像 ADD/RUN 检查、新安装 ZIP 解包后的检查以及隔离 TLS/任务回调。
- 此前手工候选包测试不替代本次修改后构建链的真实重建验证。
