## ADDED Requirements

### Requirement: Remote controller installation MUST resolve packages by detected CPU architecture

远程安装控制器时，系统必须先探测目标节点 CPU 架构，再根据操作系统、版本锚点和探测到的架构解析最终安装包。

#### Scenario: install ARM64 controller package on Linux ARM node
- **Given** 用户选择 Linux 控制器版本 `<version>`
- **And** 系统中存在该版本的 Linux `x86_64` 与 Linux `arm64` 控制器包
- **When** 远程安装探测到目标节点架构为 `arm64`
- **Then** 系统必须选择 Linux `arm64` 控制器包执行安装
- **And** 不得下发 Linux `x86_64` 控制器包

### Requirement: Bootstrap install MUST download installer and session by local architecture

用户通过 curl/bootstrap 安装控制器时，系统必须先识别本机架构，并请求对应架构的 installer 与 installer session。

#### Scenario: bootstrap install on ARM64 Linux host
- **Given** 用户在 Linux ARM64 主机执行控制器安装命令
- **When** bootstrap 脚本探测到本机架构为 `arm64`
- **Then** 系统必须请求 `arm64` 对应的 installer download 与 installer session
- **And** installer 中的包信息必须与 `arm64` 控制器包匹配
