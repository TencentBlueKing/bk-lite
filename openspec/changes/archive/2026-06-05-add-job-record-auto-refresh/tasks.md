## 1. 添加轮询逻辑

- [x] 1.1 在 `page.tsx` 中添加 `pollingTimerRef` 引用
- [x] 1.2 添加轮询 `useEffect`，当 `detail?.status` 为 `pending` 或 `running` 时启动 5 秒间隔轮询
- [x] 1.3 在 `useEffect` cleanup 中清理定时器

## 2. 验证

- [x] 2.1 手动测试：打开进行中的任务详情页，确认每 5 秒刷新一次
- [x] 2.2 手动测试：等待任务完成，确认轮询自动停止
- [x] 2.3 手动测试：点击返回按钮，确认无控制台错误（定时器已清理）
- [x] 2.4 运行 `pnpm lint && pnpm type-check` 确保无类型错误
