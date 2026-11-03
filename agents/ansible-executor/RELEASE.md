# Fusion 执行器 OpenSSL 升级构建

专用构建入口面向 Linux amd64，将 Python 固定为 3.12.15，OpenSSL 固定为
3.5.9，cryptography 固定为 46.0.5。只生成独立制品，不修改运行环境。

## 构建

准备实际链接 OpenSSL 3.5.9 的 Python 3.12.15、uv、C 编译器、make、Perl 和
Rust/Cargo。建议使用 GLIBC 2.28 基线的构建机，兼容目标部署环境；该基线并非工具
自动验证的结果。构建资源建议限制为 2 CPU / 3 GiB。

```bash
make package \
  RELEASE_PYTHON=/path/to/python3.12 \
  WORK_DIR=/path/to/new-build-directory \
  DIST_DIR=/path/to/new-dist-directory
```

`WORK_DIR` 须位于源码目录外且尚不存在，输出 `ansible-executor` 目录同样须不存在。
构建使用独立虚拟环境，不覆盖原开发环境或已有制品。

脚本按 `release-sources.json` 下载并核对 OpenSSL、cryptography 官方源码哈希。
OpenSSL 使用 `no-shared no-module` 编译为私有静态库，内置 legacy provider，
以保留 WinRM 的 NTLM/RC4 支持。`uv sync` 后安装基于该库重编译的 cryptography，
确认其 OpenSSL 版本，再执行现有单测和 PyInstaller 打包，最后用 `--help` 确认程序能启动。

可通过 `build_release.py --sources-dir /path/to/archives` 提供锁文件中的两个源码包。
其他 Python 依赖、Rust crates 和 Ansible collection 仍需可用的软件源或缓存，
该参数不代表完整离线构建。

## 接入现有构建流程

准备构建节点变量：

- `FUSION_RELEASE_PYTHON`：上述 Python 可执行文件。
- `FUSION_RELEASE_UV`：可选，默认 `uv`。
- `FUSION_RELEASE_SOURCES`：可选，离线源码目录。
- `DIST`、`WORKSPACE`：沿用流水线的制品目录及工作目录。

在 `agents/ansible-executor` 目录调用：

```bash
DIST="$DIST" bash support-files/jenkins-build-release.sh
```

输出为 `$DIST/linux/ansible-executor/`，同时复制为 `ansible-executor-amd64/`，
供现有两种 Docker context 布局取用。ARM64 须单独构建验证，不能复用 amd64 制品。

执行器不增加发行校验命令、runtime hook 或逐文件 manifest；镜像构建也不调用
额外的执行器参数。原有直接调用 PyInstaller 的流程继续保留，但只有切换到上述
新工具链、重新构建并发布制品后，才能认定运行环境的 OpenSSL 已升级。
合入源码本身不会替换旧二进制或修改在线 Jenkins。

## 验证与发布

运行 `python -m pytest tests -q`。发布前对新制品执行 Linux 任务、TLS、WinRM
及采集器启动冒烟，记录实际 OpenSSL 版本和漏洞复扫结果。完整工具链构建、ARM64
和真实 Windows 目标验收须在对应环境完成；单元测试不能替代这些验证。
