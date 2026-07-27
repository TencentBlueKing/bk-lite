# Issue #4244 ASGI 模型下载 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让六类模型下载在 Uvicorn ASGI 下以 64 KiB 分块发送，归档和响应阶段均不全量占用 Python 堆。

**Architecture:** `download_model_artifact` 继续返回磁盘临时 ZIP；共享响应构造器用仅支持异步迭代的文件包装器交给 `StreamingHttpResponse`，显式保留长度与下载头。六类 ViewSet 只负责授权、命名和调用共享构造器。

**Tech Stack:** Python 3.12、Django 4.2、asgiref、pytest、tracemalloc

## Global Constraints

- 保持 URL、权限、run 归属、文件名、`Content-Disposition`、`Content-Type` 和 ZIP 内容。
- 64 KiB 分块读取；响应关闭必须关闭底层 `TemporaryFile`。
- 只运行本 PR 修改的具体测试文件。

---

### Task 1: ASGI RED 回归

**Files:**
- Modify: `server/apps/mlops/tests/test_model_download_memory.py`
- Modify: `server/apps/mlops/tests/test_views_actions_param.py`

**Interfaces:**
- Consumes: 六类既有 `download_model` action。
- Produces: 对异步迭代、端到端堆峰值和关闭清理的回归约束。

- [ ] **Step 1: 六类响应测试断言 `response.is_async` 并通过 `response.__aiter__()` 完整消费**
- [ ] **Step 2: 增加 4 MiB 响应完整消费的 `tracemalloc` 测试，断言峰值低于输入大小**
- [ ] **Step 3: 增加未消费即 `response.close()` 仍关闭底层临时文件的测试**
- [ ] **Step 4: 运行两份具体测试，确认旧同步 `FileResponse` 因 `is_async=False` 或缺少共享构造器而 RED**

### Task 2: 共享异步文件响应

**Files:**
- Modify: `server/apps/mlops/utils/mlflow_service.py`

**Interfaces:**
- Produces: `build_model_download_response(zip_stream: BinaryIO, filename: str) -> StreamingHttpResponse`。

- [ ] **Step 1: 实现仅支持 `__aiter__`/`__anext__` 的 64 KiB 文件包装器，读取通过 `sync_to_async` 在线程中执行**
- [ ] **Step 2: 实现响应构造器，显式设置长度、内容类型和 Django 标准下载头**
- [ ] **Step 3: 让响应资源关闭器持有包装器的 `close()`，保持幂等关闭**
- [ ] **Step 4: 运行内存与共享工具具体测试，确认 GREEN**

### Task 3: 六类调用方统一

**Files:**
- Modify: `server/apps/mlops/views/anomaly_detection.py`
- Modify: `server/apps/mlops/views/classification.py`
- Modify: `server/apps/mlops/views/log_clustering.py`
- Modify: `server/apps/mlops/views/timeseries_predict.py`
- Modify: `server/apps/mlops/views/image_classification.py`
- Modify: `server/apps/mlops/views/object_detection.py`

**Interfaces:**
- Consumes: `mlflow_service.build_model_download_response`。

- [ ] **Step 1: 六类 action 用共享构造器替代各自的 `FileResponse`**
- [ ] **Step 2: 保留各自既有文件名生成与异常响应**
- [ ] **Step 3: 运行 `test_views_actions_param.py`，确认六类异步内容、头和关闭语义 GREEN**

### Task 4: 验证、提交与评审

**Files:**
- Verify: `weops/master...HEAD` 的全部变更文件。

**Interfaces:**
- Produces: clean commit、精确测试证据和 G6 分数。

- [ ] **Step 1: 运行 `git diff --check` 与三份修改测试**
- [ ] **Step 2: 提交实现并在新 commit 上重跑相同测试**
- [ ] **Step 3: 独立 G6 复评；低于 70 分则按意见继续修正**
- [ ] **Step 4: 公开文本 lint 后 push、创建带 `auto-pr` 的 PR，并回填 Issue**
