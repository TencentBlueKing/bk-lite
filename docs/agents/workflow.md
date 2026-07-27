# 日常工程工作流

## 快速路径

适用于目标清晰、机械性修改或局部缺陷：

```text
核对当前事实 -> 实现 -> 聚焦验证 -> commit/push
```

不创建 change spec，不强制 Grill。复杂或根因不明的缺陷改走 `$diagnosing-bugs`，先建立能捕获原症状的反馈回路。

## Grill 路径

当需求存在多条合理分支、跨产品或数据边界、涉及破坏性迁移，或决定难以回滚时：

```text
$grill-with-docs
  ├─ 单会话 -> $implement
  └─ 跨会话 -> $to-spec -> 仅在需要时 $to-tickets
```

- `$grill-with-docs` 一次只问一个决策问题；可从仓库得到的事实直接查。
- `$domain-modeling` 维护 `CONTEXT.md`；ADR 只记录真正难以回滚的取舍。
- `$to-spec` 只综合已收敛对话，不重新访谈。
- `$to-tickets` 只按真实阻塞边拆分可独立验证的纵向切片。
- `$implement` 使用 `$tdd`，完成后 `$code-review`，再以新鲜验证证据收口。

Grill、spec、ticket、implementation 和架构审计入口默认关闭隐式调用，日常对话不会自行进入高成本流程。

## 文档收口

一次变更最多新增一份主 change spec。完成时只更新发生变化的 capability contract、必要 ADR 和现有 change 状态；没有 sync/archive 仪式。
