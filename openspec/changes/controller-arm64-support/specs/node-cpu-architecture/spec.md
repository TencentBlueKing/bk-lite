## ADDED Requirements

### Requirement: Nodes MUST persist normalized CPU architecture

系统必须接收并保存节点上报的 CPU 架构信息，且统一归一化为业务标准值。

#### Scenario: normalize sidecar-reported architecture
- **Given** sidecar 上报 `architecture = aarch64`
- **When** server 处理节点更新
- **Then** `Node.cpu_architecture` 必须被保存为 `arm64`

### Requirement: Historical nodes MUST support CPU architecture backfill

系统必须提供管理命令，允许对历史空架构节点按需执行远程探测与回填。

#### Scenario: backfill historical node architecture with reusable credentials
- **Given** 某节点 `cpu_architecture` 为空
- **And** 系统中存在该节点最近一次控制器安装的可复用 SSH 凭据
- **When** 执行 `backfill_node_cpu_architecture`
- **Then** 系统必须远程探测该节点 CPU 架构并写回 `Node.cpu_architecture`

### Requirement: Nodes SHOULD display CPU architecture in node management

节点管理页面应展示节点 CPU 架构属性。

#### Scenario: display node architecture in node list
- **Given** 节点 `cpu_architecture = x86_64`
- **When** 用户查看节点属性
- **Then** 页面应显示 CPU 架构为 `x86_64`
