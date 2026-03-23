# nats-executor 测试与维护说明

## 目的

这个模块的测试目标不是单纯追求覆盖率，而是保护真实生产行为，避免后续改动把关键能力改坏。

当前测试体系主要围绕以下风险展开：

- 请求/响应 contract 漂移
- shell / SSH 安全回归
- timeout 与失败分类回归
- 资源泄漏
- 并发问题
- handler -> executor -> utility 组合链路被改坏

这份文档主要回答 3 个问题：

1. 现有测试分别在保护什么
2. 新增改动时应该把测试补到哪里
3. 提交前最少要跑哪些验证命令

## 测试地图

### 根目录

- `main_test.go`
  - 配置解析
  - 环境变量渲染
  - bool / string 归一化逻辑

### `local/`

- `executor_test.go`
  - 本地命令执行行为
  - exit code 透传
  - shell 选择逻辑
  - timeout 行为
  - 字符串匹配辅助函数 benchmark

- `subscriber_test.go`
  - local handler 请求解析
  - 非法 payload contract
  - download / unzip 响应 contract
  - health 响应稳定性
  - timeout / execution 错误码分类

- `regression_test.go`
  - local 核心回归测试带
  - timeout contract
  - 非法 payload contract

### `ssh/`

- `executor_test.go`
  - SCP 命令构造
  - quoting 与敏感信息脱敏
  - 兼容性 fallback 行为
  - SSH execute 错误码分类
  - 临时 key 清理与唯一性
  - 失败 / timeout 时的 cleanup
  - SCP benchmark

- `subscriber_test.go`
  - SSH handler 请求解析
  - 非法 payload contract
  - download / upload contract
  - download / upload 组合请求处理

- `regression_test.go`
  - SSH 核心回归测试带
  - 临时 key 生命周期
  - download-to-SCP 组合链路 contract

### `utils/`

- `nats_test.go`
  - 对象下载行为
  - 依赖注入 seam
  - timeout 行为
  - 必填字段校验
  - 并发请求行为
  - download benchmark

- `unzip_test.go`
  - unzip 成功 / 失败行为
  - ZipSlip 防护
  - 目录 / 文件冲突处理
  - 空压缩包处理
  - 目标目录校验
  - unzip benchmark

## 风险覆盖说明

### 1. Contract 风险

主要由 subscriber 测试和 regression 测试保护。

这些测试确保：

- 非法 payload 会返回显式失败，而不是静默丢弃
- success response 不会误带 error 元数据
- machine-readable error code 保持稳定

### 2. 安全风险

主要由 `ssh/executor_test.go` 与 `utils/unzip_test.go` 保护。

这些测试确保：

- SCP 命令 quoting 仍然安全
- password 不会在日志中泄漏
- 临时私钥文件使用方式安全
- zip 解压拒绝路径穿越

### 3. 可靠性风险

主要由 local / ssh execute 测试和 utility 测试保护。

这些测试确保：

- timeout 语义稳定
- dependency failure 分类正确
- execution failure 分类正确
- 失败时 cleanup 不会丢

### 4. 并发风险

主要由并发测试保护。

这些测试确保：

- SSH 临时 key 文件在并发下仍保持唯一
- 并发 download 调用不会共享错误状态
- 关键包在 race 检查下保持干净

### 5. 组合链路风险

主要由轻集成测试和 regression 测试保护。

这些测试确保：

- handler -> executor 链路仍然可用
- download -> SCP 执行顺序不被改坏
- 真实组合场景下 success / failure contract 不漂移

## 核心回归测试带

核心回归测试文件：

- `local/regression_test.go`
- `ssh/regression_test.go`

当前最值得长期锁住的高风险点是：

- local timeout contract
- 非法 payload contract
- SSH 临时 key 生命周期
- download-to-SCP 组合链路

如果后续重构把这些测试打坏，应该先修复这些问题，再继续扩展功能。

可以把这组测试理解为这个模块的“最小生产保护带”。

## 常见改动应该补到哪里

优先按“风险靠近代码”的原则放置：

- helper / 配置变更 -> 放到对应包已有单测文件
- handler / request contract 变更 -> 放到 `subscriber_test.go`
- 资源生命周期 / 组合链路问题 -> 放到 `regression_test.go`
- 性能敏感 helper -> 在现有 benchmark 附近补 benchmark

简单判断方式：

- **改的是单个函数行为** -> 先看对应包已有单测
- **改的是请求解析或响应格式** -> 补到 `subscriber_test.go`
- **改的是 timeout、cleanup、临时文件、组合调用链** -> 优先补到 `regression_test.go`
- **改的是高频小函数** -> 考虑补 benchmark

推荐顺序：

1. 先写失败测试
2. 再做最小修复
3. 如果是生产级问题，再补一条回归测试

## 什么时候值得做结构优化

只有当测试暴露出真实问题时，才值得动结构，比如：

- cleanup 逻辑太容易漏
- 依赖无法安全 stub / mock
- 重复分支已经导致 contract 漂移

不要为了“更优雅”而单独做大重构。

## 提交前建议检查

### 1. 常规测试

```bash
go test . ./local ./ssh ./utils ./jetstream ./logger
```

注意：这里不要使用 `go test ./...`，因为仓库内存在 `pkg/mod/` 内容，这个更大范围的模式对本模块没有实际验证价值，反而会带来噪音。

### 2. race 检查（优先针对状态更复杂的包）

```bash
go test -race ./ssh ./utils
```

### 3. 核心回归测试带

```bash
go test -run 'Regression' ./local ./ssh
```

### 4. 当前 benchmark

```bash
go test -run '^$' -bench 'Benchmark(Contains|AddLegacySCPOptions|DownloadFile|UnzipToDir)$' -benchtime=1x ./local ./ssh ./utils
```

## 实际使用原则

不要为了“测试更多”而机械加测试。

只有当新测试能够提升以下任一方面的信心时，才值得加：

- contract 稳定性
- 安全行为
- cleanup / 资源安全
- 并发安全
- 真实组合链路稳定性

## 一句话原则

先用测试暴露问题，再做最小修复；只有当测试已经证明结构有问题时，才做结构优化。
