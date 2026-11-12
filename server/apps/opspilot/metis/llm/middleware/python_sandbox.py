"""Move large tool results into the Python task workspace before compaction."""

from __future__ import annotations

import asyncio
from typing import Annotated

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import Field

from apps.opspilot.services.python_sandbox.runtime import SandboxUnavailable

SANDBOX_GUIDANCE = (
    "【本地任务工作区】Python、Shell、技能 execute 在 Server 内以子进程执行，共享本轮工作目录和依赖，每次调用是新进程。"
    "当前工作目录是 {workspace}，可用相对路径；环境变量 OPSPILOT_WORKSPACE 指向该目录。"
    "这不是容器或宿主隔离环境，命令拥有 Server 运行用户的权限。"
    "使用 Server 已安装的库和命令，不要假定系统安装了浏览器、Office 或特定字体。"
    "大 JSON 优先用 ijson 逐条读取，CSV 用 pandas chunksize，避免全量加载。"
    "HTML 使用 UTF-8 和开启 autoescape 的 Jinja2；PDF 必须显式注册可用中文字体。"
    "额外 Python 包用 python -m pip install（PIP_TARGET 已指向本轮 .packages）；"
    '若无 pip，用 uv pip install --target "$PIP_TARGET"。不要使用 --user 或改装 Server 全局环境。'
    "Node CLI 用 npm install -g，安装目录为本轮 .local，bin 已在 PATH。"
    "Python 默认超时 60 秒，Shell/技能默认 120 秒，输出最多 64 KiB。"
    "本轮结束会清理目录，文件生成后必须通过 generate_attachment_file 的 sandbox_path 保存附件。"
)


class PythonSandboxMiddleware(AgentMiddleware):
    def __init__(self, sandbox, *, threshold=4000):
        super().__init__()
        self.sandbox = sandbox
        self.threshold = threshold

        @tool
        def read_tool_result(path: str, offset: Annotated[int, Field(ge=0)] = 0) -> str:
            """分页读取本轮工具保存的完整结果。path 使用工具返回的文件路径，offset 为字符偏移，每次最多 1000 字符。

            从返回的 next_offset 继续，eof=True 表示已到文件末尾。只读结果，不执行代码或重新运行作业。
            """
            try:
                return sandbox.read_tool_result(path, offset)
            except (ValueError, SandboxUnavailable) as exc:
                return str(exc)

        self.tools = [read_tool_result]

    def _with_guidance(self, request: ModelRequest) -> ModelRequest:
        guidance = SANDBOX_GUIDANCE.format(workspace=self.sandbox.workspace)
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

    def _offload(self, request, result):
        name = str(request.tool_call.get("name", ""))
        if name in {"python_execute_direct", "read_tool_result"}:
            return result
        content = result.content if isinstance(result, ToolMessage) else result
        if not isinstance(content, str) or len(content) <= self.threshold:
            return result
        try:
            path = self.sandbox.store_result(content)
            replacement = (
                f"工具完整结果已保存至 任务工作区文件 {path}（UTF-8，共 {len(content)} 字符）。"
                "用 read_tool_result 按字符偏移分页读取；当前步骤有 python_execute_direct 时也可读取文件进行统计分析。"
                f"不要重新执行原工具来读取输出。预览：\n{content[:500]}"
            )
        except SandboxUnavailable:
            # Preserve the full result on failure; never claim it was saved.
            return result
        if isinstance(result, ToolMessage):
            return result.model_copy(update={"content": replacement})
        return replacement

    def wrap_tool_call(self, request, handler):
        return self._offload(request, handler(request))

    async def awrap_tool_call(self, request, handler):
        result = await handler(request)
        return await asyncio.to_thread(self._offload, request, result)
