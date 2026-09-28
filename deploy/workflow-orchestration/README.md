# 编排中心本地运行时

本目录启动固定版本的 Conductor OSS 3.32.1。BK-Lite 保存并发布原生 Conductor
DSL，独立 Conductor Worker 执行编排原子；Conductor 不进入 `batch_init` 启动依赖。
主机脚本仍由 JobMgmt 创建作业，并交给 JobMgmt 默认 Celery Worker 与 Ansible executor
执行，编排中心不创建 Celery 队列。

文档生成在 Server/Worker 进程内完成：Word 使用 docxtpl，Excel 使用 xlsxjinja，
不再依赖 Carbone 容器。

## 初始化

```bash
cd server
UV_CACHE_DIR=/private/tmp/bklite-uv-cache uv run python manage.py migrate workflow_orchestration
UV_CACHE_DIR=/private/tmp/bklite-uv-cache uv run python manage.py init_realm_resource
UV_CACHE_DIR=/private/tmp/bklite-uv-cache uv run python manage.py init_custom_menu

cd ../deploy/workflow-orchestration
make init
make validate
make up
make check
```

Server 使用以下运行期地址：

```bash
CONDUCTOR_BASE_URL=http://127.0.0.1:8091/api
```

## 启动 Worker

Worker 在独立终端运行，不加入 Server 初始化阶段：

```bash
cd server
CONDUCTOR_BASE_URL=http://127.0.0.1:8091/api \
UV_CACHE_DIR=/private/tmp/bklite-uv-cache \
uv run python manage.py run_workflow_worker
```

## 页面验收

打开 `http://localhost:3000/workflow-orchestration`：

1. 新建主机健康巡检流程；
2. 检查 Linux/Windows 脚本、健康阈值和 Word/Excel 模板；
3. 保存并发布原生 Conductor DSL；
4. 从当前组织选择最多 100 台节点管理主机并执行；
5. 在执行详情核对作业任务 ID、逐节点结果和“成功（有告警）”；
6. 下载 Word/Excel 巡检报告并核对多磁盘数据。

目标授权由节点管理校验，真实副作用、危险命令检查和逐目标执行记录由作业平台负责。
报告产物写入对象存储，默认保留 30 天。停止本地 Conductor 使用 `make down`。
