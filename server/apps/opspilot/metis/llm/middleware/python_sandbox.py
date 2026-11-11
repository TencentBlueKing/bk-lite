"""Move large tool results into the Python task workspace before compaction."""

from __future__ import annotations

import asyncio

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import SystemMessage, ToolMessage

from apps.opspilot.services.python_sandbox.runtime import SandboxUnavailable

SANDBOX_GUIDANCE = (
    "【任务容器】Python、Shell、技能 execute 共享 /workspace 文件及本轮安装的依赖，每次调用是新进程。"
    "默认镜像提供 requests、pandas、lxml、matplotlib、文档库和 zip/unzip/file；"
    "大 JSON 用 ijson 逐条读取，CSV 用 pandas chunksize，避免全量加载或把迭代器转成 list。"
    "HTML 用 jinja2（开启 autoescape）及 markdown_it，PDF 用 ReportLab 并显式注册中文字体。"
    "详细示例和字体路径见 /opt/opspilot-sandbox/USAGE.md。"
    "额外 Python 包用 python -m pip install --user，Node CLI 用 npm install -g；"
    "两者安装目录为 /workspace/.local，bin 已在 PATH。Node 库在脚本目录 npm install。"
    "当前限制为 1 GiB 内存、1 CPU、256 MiB 工作目录、128 MiB 临时目录；及时清理自己的中间文件和安装缓存。"
    "文件生成后通过 generate_attachment_file 的 sandbox_path 保存附件。"
)


class PythonSandboxMiddleware(AgentMiddleware):
    def __init__(self, sandbox, *, threshold=4000):
        super().__init__()
        self.sandbox = sandbox
        self.threshold = threshold

    @staticmethod
    def _with_guidance(request: ModelRequest) -> ModelRequest:
        system = request.system_message
        if system is None:
            system = SystemMessage(content=SANDBOX_GUIDANCE)
        else:
            blocks = list(system.content) if isinstance(system.content, list) else [{"type": "text", "text": system.content}]
            system = system.model_copy(update={"content": [*blocks, {"type": "text", "text": SANDBOX_GUIDANCE}]})
        return request.override(system_message=system)

    def wrap_model_call(self, request, handler):
        return handler(self._with_guidance(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._with_guidance(request))

    def _offload(self, request, result):
        name = str(request.tool_call.get("name", ""))
        if name == "python_execute_direct":
            return result
        content = result.content if isinstance(result, ToolMessage) else result
        if not isinstance(content, str) or len(content) <= self.threshold:
            return result
        try:
            path = self.sandbox.store_result(content)
            replacement = f"工具完整结果已保存至 Python 沙箱文件 {path}（UTF-8），可用 python_execute_direct 读取。预览：\n{content[:500]}"
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
