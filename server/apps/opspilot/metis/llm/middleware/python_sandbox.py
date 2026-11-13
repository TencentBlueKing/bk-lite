"""Provide instructions for the shared local task workspace."""

from __future__ import annotations

import posixpath
from pathlib import Path

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import SystemMessage, ToolMessage

from apps.opspilot.services.python_sandbox.result_backend import RESULT_PATH

SANDBOX_GUIDANCE = (
    "【本地任务工作区】Python、Shell、技能 execute 在 Server 内以子进程执行，共享本轮工作目录和依赖，每次调用是新进程。"
    "当前工作目录是 {workspace}，可用相对路径；环境变量 OPSPILOT_WORKSPACE 指向该目录。"
    "这不是容器或宿主隔离环境，命令拥有 Server 运行用户的权限。"
    "使用 Server 已安装的库和命令，不要假定系统安装了浏览器、Office 或特定字体。"
    "原生 /large_tool_results/ 路径对应当前目录下同名目录，可用 read_file/grep 查阅结果；读取不需要重新执行业务工具。"
    "大 JSON 优先用 ijson 逐条读取，CSV 用 pandas chunksize，避免全量加载。"
    "HTML 使用 UTF-8 和开启 autoescape 的 Jinja2；PDF 必须显式注册可用中文字体。"
    "额外 Python 包用 python -m pip install（PIP_TARGET 已指向本轮 .packages）；"
    '若无 pip，用 uv pip install --target "$PIP_TARGET"。不要使用 --user 或改装 Server 全局环境。'
    "Node CLI 用 npm install -g，安装目录为本轮 .local，bin 已在 PATH。"
    "Python 默认超时 60 秒，Shell/技能默认 120 秒，输出最多 64 KiB。"
    "本轮结束会清理目录，文件生成后必须通过 generate_attachment_file 的 sandbox_path 保存附件。"
)


class PythonSandboxMiddleware(AgentMiddleware):
    def __init__(self, sandbox):
        super().__init__()
        self.sandbox = sandbox

    def _with_guidance(self, request: ModelRequest) -> ModelRequest:
        guidance = SANDBOX_GUIDANCE.format(workspace=self.sandbox.workspace)
        files = self.sandbox.files()
        if files:
            guidance += "本轮已保存结果：" + ", ".join(RESULT_PATH + Path(path).name for path in files)
        system = request.system_message
        if system is None:
            system = SystemMessage(content=guidance)
        else:
            blocks = list(system.content) if isinstance(system.content, list) else [{"type": "text", "text": system.content}]
            system = system.model_copy(update={"content": [*blocks, {"type": "text", "text": guidance}]})
        return request.override(system_message=system)

    def wrap_model_call(self, request, handler):
        return handler(self._with_guidance(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._with_guidance(request))

    def _deny_result_mutation(self, request):
        call = request.tool_call
        if call.get("name") not in {"write_file", "edit_file"}:
            return None
        path = posixpath.normpath("/" + str((call.get("args") or {}).get("file_path") or "").lstrip("/"))
        physical = self.sandbox.workspace + RESULT_PATH
        if path.startswith(RESULT_PATH) or path.startswith(physical):
            return ToolMessage(content="已保存的工具结果只读。", tool_call_id=call.get("id", ""), name=call["name"], status="error")
        return None

    def wrap_tool_call(self, request, handler):
        denied = self._deny_result_mutation(request)
        return denied if denied is not None else handler(request)

    async def awrap_tool_call(self, request, handler):
        denied = self._deny_result_mutation(request)
        return denied if denied is not None else await handler(request)
