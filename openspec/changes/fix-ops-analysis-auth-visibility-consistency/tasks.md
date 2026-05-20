## 1. Directory Write Authorization

- [ ] 1.1 确认 `DirectoryModelViewSet.create/update/partial_update` 当前绕过 `AuthViewSet` 的具体差异点（组织字段校验、`current_team` 校验、实例级 `Operate` 校验）。
- [ ] 1.2 调整 `DirectoryModelViewSet.create`，移除 ORM 直写主路径，改为在目录特有校验后调用 `super().create()`。
- [ ] 1.3 调整 `DirectoryModelViewSet.update` 与 `partial_update`，保留内置目录只读限制，但改为在校验后调用 `super().update()` / `super().partial_update()`。
- [ ] 1.4 确认目录写接口仍然维持 `is_build_in` / `build_in_key` 只读语义，不允许客户端借写接口修改。

## 2. Container Visibility Consistency

- [ ] 2.1 梳理 dashboard/topology/architecture 保存时的目标 `groups` 与目标目录解析路径，覆盖 create/update/partial_update 三种场景。
- [ ] 2.2 新增共享的目录链一致性校验逻辑：从目标目录向上遍历祖先目录并检查目标 `groups` 是否被整条目录链覆盖。
- [ ] 2.3 在 dashboard/topology/architecture 保存前接入该校验，目录链不满足时拒绝保存。
- [ ] 2.4 设计并实现结构化错误反馈，至少包含冲突目录和缺失组织信息，便于前端展示。

## 3. Regression Coverage

- [ ] 3.1 补充目录写接口测试：无权写入目标组织时被拒绝；无实例级操作权时被拒绝；有权限时允许写入。
- [ ] 3.2 补充画布保存测试：对象 `groups` 超出直属目录 `groups` 时被拒绝；超出祖先目录 `groups` 时被拒绝；目录链完整覆盖时允许保存。
- [ ] 3.3 验证切组后目录树表现：符合目录链约束的对象在目标组织中可发现，不符合约束的对象无法保存进入系统。

## 4. Verification

- [ ] 4.1 运行 `operation_analysis` 相关后端测试或最小验证命令，确认目录写授权与目录链校验行为符合预期。
- [ ] 4.2 人工验证侧边栏切组场景，确认问题从“保存成功但切组后消失”收敛为“保存前被明确阻止”。
- [ ] 4.3 更新变更说明，明确本次不包含数据源保存时前置一致性校验，继续沿用现有运行时数据源访问控制。
