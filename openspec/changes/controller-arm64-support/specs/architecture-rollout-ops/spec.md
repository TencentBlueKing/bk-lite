## ADDED Requirements

### Requirement: Rollout verification MUST confirm required multi-architecture artifacts

系统必须提供发布校验命令，确认 installer 与控制器包的多架构产物是否齐备。

#### Scenario: verify Linux x86_64 and ARM64 rollout artifacts
- **Given** 运维已上传 Windows `x86_64` installer、Linux `x86_64` installer、Linux `arm64` installer
- **And** 已上传指定版本的 Linux `x86_64` 与 Linux `arm64` 控制器包
- **When** 执行 `verify_architecture_rollout --version <version>`
- **Then** 系统必须确认上述 installer 与控制器包存在
- **And** 输出当前仍为空架构的节点数量

### Requirement: Installer upload MUST support explicit CPU architecture

installer 上传命令必须显式支持 CPU 架构参数，以便分别上传 Linux `x86_64` 与 Linux `arm64` installer。

#### Scenario: upload Linux ARM64 installer
- **Given** 运维执行 `installer_init --os linux --cpu_architecture arm64`
- **When** 上传 installer 文件
- **Then** installer 必须存储到 Linux `arm64` 对应的 latest path

### Requirement: Historical backfill SHOULD skip nodes without reusable credentials

历史节点架构回填命令在没有可复用安装凭据时应跳过节点，而不是猜测默认架构。

#### Scenario: skip node without credentials during backfill
- **Given** 某历史节点 `cpu_architecture` 为空
- **And** 系统中没有该节点可复用的安装凭据
- **When** 执行 `backfill_node_cpu_architecture`
- **Then** 系统应跳过该节点
- **And** 不得将其架构默认写成 `x86_64`
