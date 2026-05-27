## Why

MLOPS 当前已经引入 `AlgorithmConfig` 作为统一算法配置表，但没有默认数据初始化链路，部署后需要依赖手工创建配置或运行时镜像兜底。现在需要补齐一个首装可执行、对用户已有数据安全的初始化机制，让内置算法配置能够从仓库默认文件首次写入数据库。

## What Changes

- 新增 MLOPS 默认算法配置初始化能力，从仓库内置 JSON 文件导入 `AlgorithmConfig`。
- 约束默认配置文件目录结构、文件命名和顶层字段格式，保证初始化输入稳定可控。
- 在初始化时按 `(algorithm_type, name)` 做首次幂等写库：不存在则创建，已存在则跳过。
- 将该初始化命令接入 MLOPS 模块初始化入口，并保持对全局 `batch_init` 非阻塞。
- 为初始化过程增加控制台与模块日志，输出创建、跳过和非法文件汇总。

## Capabilities

### New Capabilities
- `mlops-algorithm-config-bootstrap`: Bootstrap default MLOPS algorithm configuration records from support-files JSON using non-destructive, first-write initialization.

### Modified Capabilities

None.

## Impact

- Affected code:
  - `server/apps/mlops/management/commands/`
  - `server/apps/mlops/support-files/algorithm-configs/`
  - `server/apps/core/management/commands/batch_init.py`
- Affected systems:
  - MLOPS algorithm configuration bootstrap flow
  - Server startup batch initialization flow
- No new external dependencies are required.
- No breaking API changes are expected.
