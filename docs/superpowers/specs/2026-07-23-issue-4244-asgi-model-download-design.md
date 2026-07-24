# Issue #4244 ASGI 模型下载设计

## 目标

六类 MLOps 模型下载在生产 Uvicorn ASGI 链路中以固定大小分块发送，避免归档和响应阶段将完整 ZIP 物化到 Python 堆，同时保持现有 HTTP、权限和 ZIP 契约。

## 事实与约束

- 六类 ViewSet 共用 `download_model_artifact`，生产入口由 Uvicorn ASGI 承载。
- Django 4.2 对同步 `FileResponse` 的 ASGI 消费会先把所有分块收集为列表，不能作为端到端流式方案。
- URL、权限、run 归属、文件名、`Content-Disposition`、`Content-Type`、ZIP 条目和内容必须保持不变。
- 归档异常和临时盘失败继续进入现有异常处理；不得新增兼容开关或协议版本。

## 方案

在 `mlflow_service` 共享层保留磁盘 `TemporaryFile` 归档，并增加 64 KiB 异步文件迭代器与响应构造器。迭代器通过线程桥接执行阻塞读取，只暴露异步迭代协议，使 Django ASGI 逐块消费；响应显式设置文件长度和下载头，并登记底层临时文件的关闭回调。

六类 ViewSet 统一调用该响应构造器，不各自管理 Django 响应类型。这样响应完成或 ASGI 断连触发 `response.close()` 时，底层临时 ZIP 被关闭；归档过程中失败仍由 `download_model_artifact` 立即关闭。

## 数据流

1. ViewSet 完成既有对象授权和 run 归属校验。
2. `download_model_artifact` 下载 artifact 并把 ZIP 写入磁盘临时文件。
3. 共享响应构造器计算剩余长度、设置下载头，并返回异步流式响应。
4. ASGI handler 以 64 KiB 分块发送；完成或断连后关闭响应及临时文件。

## 测试

- RED：旧同步 `FileResponse` 经 `response.__aiter__()` 完整消费时产生迭代器类型告警，且 Python 堆峰值随输入增长。
- GREEN：相同输入经异步响应消费不出现同步迭代告警，峰值低于输入大小。
- 六类下载入口验证状态、文件名、内容类型、长度、ZIP 字节、异步迭代和 `close()` 清理。
- 共享工具继续覆盖目录、单文件、路径不存在及归档异常关闭。

## 风险与回滚

- 风险从内存转移到临时盘容量；磁盘满继续按既有 500 错误契约返回，不改变 API。
- WSGI 同步消费异步响应会回退为全量消费，但当前生产部署为 ASGI；行为不差于旧实现。
- 回滚可整体还原共享响应构造器和六类调用点，不涉及数据迁移。
