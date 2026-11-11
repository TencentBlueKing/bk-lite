# OpsPilot 统一执行容器

Python 工具、`shell_execute` 和 DeepAgents 技能 `execute` 使用同一任务容器、同一 `/workspace`。
正式入口不再实例化 `LocalShellBackend`，也不在 Server 上安装技能依赖。

```sh
docker build -t bk-lite-python-sandbox:latest agents/opspilot-python-sandbox
```

Server 使用 Docker SDK 的 `DOCKER_HOST` 等配置；`OPSPILOT_PYTHON_SANDBOX_IMAGE`
可以指定预构建镜像。镜像包含 Python、uv/uvx、Node/npm/npx、curl 及常用文档库和中文字体。
技能声明的 requirements.txt、package.json 和 Python 依赖按需安装在容器中。
容器不挂载宿主目录或 Docker socket，不继承 Server 环境，只注入对应技能的运行参数。
Docker 或镜像不可用时明确失败，不回退到宿主执行。沙箱不参与 Server 启动依赖。

每轮首次需要执行或文件操作时创建容器，结束、异常或取消时销毁，最长存活一小时。
网络保留 Docker 默认能力；部署使用容器内部的 MinIO 服务名时，通过
`OPSPILOT_SANDBOX_NETWORK` 指定同一个已有 Docker 网络。它只决定网络连通性，不添加出站限制。
Python 单次执行 60 秒、技能默认 120 秒、PPT 导出 180 秒，输出最多 64 KiB。
工作目录 256 MiB，单次文件导出最多 16 MiB，上传附件按现有 20 MiB 上限读取。
技能资源批量传输上限为 128 MiB / 20000 个文件。

## 轻量扩展

保持 1 GiB 内存、1 CPU、256 MiB 工作目录、128 MiB 临时目录和 128 进程上限。
新增 zip/unzip（附件压缩）、file（格式识别）、Jinja2 和 markdown-it-py（HTML 报告）、
ijson（大 JSON 流式分析）；显式声明已有的 requests，避免仅依赖其他库间接安装。
不预装浏览器、Office 渲染引擎或新的大型数据分析框架。

Python 使用 `python -m pip install --user`，用户包在 `/workspace/.local`，默认禁用 pip 下载缓存。
npm 全局 CLI 也安装到 `/workspace/.local`，共享其 bin PATH；Node 脚本库仍在脚本目录本地安装。
npm/uv 缓存分别在 `/workspace/.cache/npm`、`/workspace/.cache/uv`，均随任务销毁。
这些配置由镜像统一提供给 Python、Shell 和技能，不创建宿主依赖或额外虚拟环境。

[容器使用说明](USAGE.md)安装到 `/opt/opspilot-sandbox/USAGE.md`；模型调用的沙箱中间件
提供简短执行指引，包含流式分析、安装方法、中文字体和附件保存方式，无需提前启动容器。
已有镜像需要重新构建并发布，Server 应使用同一版本代码和镜像。

## 当前会话附件

渠道入口先校验会话身份、上传者和团队，再签发一小时有效的附件授权。
执行前再次核对上传文件的归属、会话和状态。历史生成附件只从当前已授权会话的
服务端助手消息中提取、校验平台签名及执行 ID，不根据模型给出的文件 ID 扩大范围。
清单最多包含最近 100 个上传附件及最近 100 条助手消息中的 100 个生成附件。
调试入口只授权当轮通过上传权限校验的附件；IM 入口支持其会话历史生成附件。

容器只接收单对象、一小时有效的 MinIO GET 签名地址，不能列桶或覆盖存储对象。
只提供清单，不批量回灌文件，也不挂载整个附件目录：

```sh
cat /workspace/attachments/index.json
python /workspace/attachments/read.py upload-123
# 返回 /workspace/attachments/downloads/upload-123/<文件名>
```

这是按需下载到任务目录的读取方式，不是透明文件系统挂载。
可以通过 Python 或技能修改本地副本，将产物写入 `/workspace`，然后调用现有工具：

```python
generate_attachment_file(filename="report.html", file_type="html", sandbox_path="/workspace/report.html")
```

工具将文件原始字节保存到 `WorkflowAttachmentAsset` 使用的真实 MinIO 存储，返回现有签名下载入口。
原始附件保持不变；下一轮从会话中取得上轮产物，再修改并生成新版本。
PPT 技能脚本和自动导出也在同一个容器执行。服务端只接收有界产物用于既有 SVG 校验与附件登记。

## 验证

从 `server/` 运行；本地需要 Docker、上面构建的镜像，以及 PATH 中的 `minio`：

```sh
PYTHONPATH=. .venv/bin/python apps/opspilot/tests/integration/verify_container_attachments.py
OPSPILOT_TEST_DOCKER=1 DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=test ENABLE_CELERY=true \
  .venv/bin/pytest apps/opspilot/tests/test_python_sandbox.py --no-cov
OPSPILOT_TEST_DOCKER=1 DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=test ENABLE_CELERY=true \
  .venv/bin/pytest apps/opspilot/tests/test_sandbox_lightweight.py apps/opspilot/tests/test_shell_sandbox.py --no-cov
```

轻量镜像测试覆盖落盘 JSON → ijson 统计 → 中文 HTML/PDF → ZIP 打包解包，
以及非 root 用户安装本地测试 Python/Node 包后跨工具使用和任务隔离。
安装测试使用自建 wheel/Node 包，不依赖外部软件仓库；大文件测试验证分块读取时的进程内存。

纵向验证脚本创建临时 MinIO、随机凭据和独立 SQLite，使用固定模型响应驱动真实异步工具链，
覆盖正式技能 backend、会话授权、
按需读取、技能修改、Python 复读、真实附件存储、签名下载、下一轮二次修改及容器回收。
不会访问业务桶；结束后删除测试服务和数据。容器需能访问本机测试地址，必要时用
`OPSPILOT_TEST_STORAGE_HOST` 指定两端都能访问的本机地址。

`shell_execute(commands)` 保留原有工具名与命令列表参数。列表沿用同一 shell 顺序执行的语义，
`cd` 和变量只在本次列表内延续；跨工具调用共享工作目录文件，不保留 shell 进程状态。
迁移后宿主路径、宿主程序和宿主环境变量不再可用，原有命令黑名单由容器隔离替代。
不新增网络限制；Shell 批次沿用容器的 120 秒超时及 64 KiB 输出上限。
回滚代码时需同步评估旧版 ShellTool 会恢复本地执行，不提供自动宿主回退开关。
