# OpsPilot 本地执行工作区

## 决定与范围

2026-11-12：取消每轮创建容器，Python、Shell、技能 execute 在 Server 内通过子进程执行。
删除 `agents/opspilot-python-sandbox` 镜像、Docker SDK 创建/执行/删除逻辑及其专用配置；不新增执行服务、Pod 或网络授权开关。
历史 `PythonSandbox`、`python_sandbox` 和 `sandbox_path` 名称保留，表示任务工作区，不再表示系统隔离。

## 运行契约

- 每次 DeepAgent 节点运行一个工作区，首次访问才建立 `opspilot-run-*` 临时目录；没有启动期依赖。
- 工具返回超过 4,000 字符的字符串时直接落盘，以路径和 500 字符预览代替完整上下文；落盘失败保留原结果。
- Python 使用 Server 的 Python 解释器；Shell 使用 Server PATH 中的 `sh`。技能文件由本地文件后端准备，`execute` 与两个工具共享目录及依赖。
- 不创建全局 `/workspace` 或 `/skills` 链接。模型收到本轮真实路径，执行可使用相对路径或 `OPSPILOT_WORKSPACE`。
  技能工具的 `/skills`、`/ppt-workspace` 别名映射到本轮目录；技能脚本内部应使用相对路径或该环境变量。
- Python 默认 60 秒，Shell/技能默认 120 秒，PPT 导出 180 秒；合并输出 64 KiB。
  调用退出、超时和工作区关闭时回收普通子进程组，关闭后不再接纳执行，随后清理工作目录。
- 当前会话附件授权逻辑不变，清单只包含允许读取的对象临时 GET URL。读取脚本按 ID 下载；修改通过 `generate_attachment_file(sandbox_path=本轮绝对路径)` 保存新附件。
- 附件读写接口只接纳当前目录的普通文件，拒绝越界及逃逸链接，单文件上限 16 MiB；技能物化保留 128 MiB / 20,000 文件上限。
- Server 环境变量不整包透传。技能参数仍按包注入和脱敏；HOME/TMPDIR、Python 包与 npm CLI/cache 路径指向本轮目录。
- Python 增量依赖使用 `python -m pip install`，由 `PIP_TARGET` 指向 `.packages`；Server 无 pip 时使用
  `uv pip install --target "$PIP_TARGET"`。不使用 `--user`，不自动安装到 Server 全局 Python 环境。

## 明确不再提供的保证

本方案按产品决定允许代码使用 Server 运行用户的系统权限。临时目录、环境变量筛选、文件工具路径检查均不是安全沙箱。
Python/Shell 可访问该用户有权限的其他文件及网络；不新增 import、open、subprocess、curl 黑名单。
原容器 1 GiB 内存、1 CPU、256 MiB 工作目录和 PID 限额不再存在。
进程组回收不是恶意程序隔离，主动脱离进程组的程序及 Server 被强制终止时的残留不保证回收。

## 部署与迁移

1. 部署新 Server 代码并安装 `.[opspilot]` 依赖（新增 ijson，保留流式处理大 JSON 的能力）。Python 和技能共用这些依赖。
2. Server 运行环境须有 `sh`；curl、Node/npm、zip/unzip、Poppler、中文字体按技能需要在 Server 环境提供。
   Docker/Kubernetes 部署放在 Server 镜像中，主机部署放在 Server 所在主机；不再构建额外执行镜像。
3. 不再使用 `OPSPILOT_PYTHON_SANDBOX_IMAGE`、`OPSPILOT_SANDBOX_NETWORK`。仅为旧任务沙箱设置的 Docker socket/权限可由部署方移除；其他模块所需配置不受此变更管理。
4. 等待旧版本在途任务结束再停止旧实例。新代码不删除部署环境已有容器，未保存的旧工作区文件不迁移；已保存附件仍可继续读取。
5. 不新增 batch_init 操作或 Supervisor 服务。

回滚：回退本变更，并恢复原执行镜像及 Docker 连接配置。无数据库迁移，已保存附件不受影响。

## 验证

本地回归覆盖真实子进程、结果文件共享、技能文件操作、超时/取消清理、路径检查、中文输出、增量依赖及 PPT 导出。
原 Docker 测试转换为无需 Docker 的常规回归。

真实对象存储纵向验证（仅创建临时 MinIO 数据目录、临时凭据和 SQLite 数据库）：

```sh
cd server
PYTHONPATH=. .venv/bin/python apps/opspilot/tests/integration/verify_local_attachments.py
```

该脚本使用真实工具与存储；模型仅按固定顺序发出工具调用，不调用外部 LLM。
验证会话/用户/团队授权、Shell curl 下载、技能修改、Python 读取、保存附件、下一轮再编辑与目录清理。

2026-11-12 本地验证结果：202 项相关测试通过，运行时及落盘中间件覆盖率 84.68%；
真实 MinIO 附件纵向验证通过，包含下一轮再编辑；Black、isort、flake8 与 `git diff --check` 通过。
测试使用 SQLite `--nomigrations`：完整迁移链在无关 APM 迁移中报
`NewApmIngestSourceOrganization has no field named 'ingest_source'`，因此本次没有验证完整数据库迁移。
另排除一项已在修改前 `node.py` 上复现的基线失败：
`TestBuildDeepagentNodes.test_unresolved_k8s_target_skips_namespace_required_followup_without_replan`
（预期 3 次可见工具步骤，实际 4 次）。本变更不修改该规划行为。
