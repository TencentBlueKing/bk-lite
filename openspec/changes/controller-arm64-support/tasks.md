## 1. 数据模型与兼容

- [x] 1.1 为 `Node` 新增 `cpu_architecture`
- [x] 1.2 为 `Controller` 新增 `cpu_architecture`
- [x] 1.3 为 `PackageVersion` 新增 `cpu_architecture`
- [x] 1.4 为 `ControllerTaskNode` 新增 `cpu_architecture` 与 `resolved_package_version_id`
- [x] 1.5 历史 `Controller` / `PackageVersion` 数据回填 `x86_64`

## 2. 安装链路

- [x] 2.1 远程安装前按目标节点架构探测并解析实际包
- [x] 2.2 bootstrap/curl 安装按本机架构获取 installer 与 session
- [x] 2.3 installer metadata / manifest 支持按架构返回

## 3. 节点与版本发现

- [x] 3.1 sidecar 回调将 `architecture` 归一化并写入 `Node.cpu_architecture`
- [x] 3.2 节点属性展示 CPU 架构
- [x] 3.3 版本发现按架构优先匹配控制器定义与最新版本

## 4. 运维发布能力

- [x] 4.1 `installer_init` 支持 `--cpu_architecture`
- [x] 4.2 `controller_package_init` / `collector_package_init` 支持 `--cpu_architecture`
- [x] 4.3 sidecar-installer 构建支持 Linux x86_64 / ARM64 发布产物
- [x] 4.4 新增 `verify_architecture_rollout`
- [x] 4.5 新增 `backfill_node_cpu_architecture`
- [x] 4.6 补充 rollout checklist 与回填说明文档

## 5. 验证

- [x] 5.1 补充自动化测试：架构归一化、包解析、installer/session、remote install、sidecar 回调、view/open_api、发布命令、backfill 命令
- [x] 5.2 运行 `uv run pytest apps/node_mgmt/tests/test_architecture_support.py -q`
- [ ] 5.3 手动验证 Linux x86_64 curl 安装
- [ ] 5.4 手动验证 Linux ARM64 curl 安装
- [ ] 5.5 手动验证 Linux x86_64 远程安装
- [ ] 5.6 手动验证 Linux ARM64 远程安装
- [ ] 5.7 手动验证发布校验与历史节点回填在真实环境中的表现
