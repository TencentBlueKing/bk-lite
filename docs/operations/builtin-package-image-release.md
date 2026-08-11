# 内置控制器与采集器包镜像发布 Runbook

本文约束用于生成 BK-Lite 内置控制器、采集器和安装器包的镜像发布流程，重点防止
单一架构镜像覆盖共享标签后，部署环境无法生成 `/apps/pkgs`，继而在包初始化阶段
产生连续的 `FileNotFoundError`。

## 1. 阶段与责任边界

内置包发布分为三个阶段，必须按顺序执行：

1. **构建期**：生成二进制和安装器，并构建承载这些源产物的镜像。
2. **部署准备期**：从镜像导出 `/apps/pkgs`，校验清单、大小和摘要，再初始化对象存储。
3. **Server 启动期**：只消费已经通过部署准备期校验的结果，不负责补偿失败的镜像构建、
   跨架构导出或对象存储发布。

包导出或对象初始化失败必须使当前发布失败。禁止在源文件缺失时继续执行后续
`controller_package_init`、`collector_package_init` 或 `installer_init`，否则首个根因会被
大量次生的文件不存在错误掩盖。

Server 启动期和运行期的完整边界见
[Server 启动顺序与服务依赖边界](server-startup-dependencies.md)。

## 2. 镜像架构发布规则

默认安装流程使用共享镜像标签时，发布流水线必须满足以下规则：

- 共享标签至少包含默认部署所需的 `linux/amd64` manifest；不得用仅包含
  `linux/arm64` 的镜像覆盖供 amd64 环境使用的 `latest`。
- 同时支持 amd64 和 arm64 时，应发布包含两个平台的 manifest list；如果某个架构尚不
  支持内置包生成，则使用显式架构标签，并且不得将其提升为默认共享标签。
- 构建和运行平台必须显式传递，不得依赖流水线 Runner 的本机架构推断。
- 镜像必须写入 `org.opencontainers.image.revision`、`org.opencontainers.image.created`
  和版本标签，以便从故障镜像追溯源码提交与构建任务。
- 提升或覆盖 `latest` 前先完成不可变版本标签的验证；验证失败时保留原 `latest`。

发布前可使用以下命令核对 manifest，实际镜像名由流水线注入：

```bash
docker buildx imagetools inspect "$FUSION_COLLECTOR_IMAGE"
docker buildx imagetools inspect "$TELEGRAF_IMAGE"
docker buildx imagetools inspect "$NATS_EXECUTOR_IMAGE"
```

验收输出必须明确列出目标部署平台。只显示 `linux/arm64` 的共享标签不得用于 amd64
安装环境。

## 3. fusion-collector 源产物校验

对默认 amd64 安装流程，流水线必须在提升镜像标签前以 `linux/amd64` 运行镜像，并至少
校验以下源产物存在且非空：

```text
/opt/fusion-collectors/misc/VERSION
/opt/fusion-collectors/bin/telegraf
/opt/fusion-collectors/bin/vector
/opt/fusion-collectors/bin/nats-executor
/opt/release/linux/fusion-collectors/bklite-controller-installer
/opt/release/windows/fusion-collectors/bklite-controller-installer.exe
/opt/release/windows/fusion-collectors/bin/telegraf.exe
/opt/release/windows/fusion-collectors/bin/vector.exe
/opt/release/windows/fusion-collectors/bin/nats-executor.exe
```

校验不能只检查镜像能否拉取或容器能否进入 `Started` 状态。平台不匹配警告、容器
启动和源产物可导出是三个不同条件。

建议流水线记录每个产物的路径、字节数和 SHA-256。包导出应写入临时目录，全部成功后
再原子替换正式 `pkgs` 目录，避免失败构建留下“目录存在但内容不完整”的状态。

## 4. 部署准备期门禁

开始包初始化前必须同时通过以下检查：

- [ ] 部署主机架构与待执行镜像的目标平台一致。
- [ ] 镜像 manifest 包含目标平台，并且镜像摘要与本次发布记录一致。
- [ ] `/apps/pkgs/controller/VERSION` 存在并能读取 Linux、Windows 控制器版本。
- [ ] Linux、Windows 控制器压缩包存在且非空。
- [ ] Linux、Windows 的内置采集器文件存在且非空。
- [ ] Linux、Windows GUI 安装器存在且非空。
- [ ] 每个初始化命令失败都会立即终止发布，后续命令不会继续执行。
- [ ] 对象存储中的对象大小和 SHA-256 与本次构建记录一致。

Windows 远程安装使用的 `bklite-controller-bootstrap.exe` 是独立发布产物，不得因为
fusion-collector 镜像或 GUI 安装器校验通过而省略。它的构建、上传和验收见
[Windows 控制器远程安装发布 Runbook](windows-controller-remote-install-release.md)。

## 5. 常见失败与定位

| 现象 | 优先检查 |
|---|---|
| Docker 提示 requested image platform 与 host platform 不匹配 | 共享标签是否被单一架构镜像覆盖，manifest 是否包含目标平台 |
| `/apps/pkgs/controller/VERSION` 不存在 | fusion-collector 包导出是否真正成功，是否在失败后仍进入初始化阶段 |
| 所有 collector 和 installer 连续报 `FileNotFoundError` | 先定位包导出的第一个错误，不要逐个补文件或忽略异常 |
| 镜像内存在源文件但宿主机 `pkgs` 为空 | volume 路径、跨架构执行和导出命令退出码是否正确 |
| 无法确认镜像对应哪个提交 | 检查 OCI revision 标签；缺失时回查发布任务并补齐流水线元数据 |

## 6. 回滚

发布门禁失败时，不得覆盖当前可用的共享标签。若错误镜像已经发布：

1. 将共享标签恢复到上一已验证的镜像摘要，或在部署配置中临时固定该摘要。
2. 清理本次失败生成的不完整临时包目录，不复用其中任何文件。
3. 使用恢复后的镜像重新导出全部包并执行完整校验。
4. 重新初始化对象存储后再恢复后续部署步骤，保留故障镜像摘要和流水线日志用于追踪。
