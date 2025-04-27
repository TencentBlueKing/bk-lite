import os
import traceback

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.constants import END
from langgraph.graph import MessagesState

from src.core.entity.basic_llm_request import BasicLLMReuqest
from src.core.graph.basic_graph import BasicGraph


class ToolsGraph(BasicGraph):

    def should_continue(self, state: MessagesState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools"
        return END

    async def invoke(self, graph, request: BasicLLMReuqest):
        config = {
            "graph_request": request,
            "recursion_limit": 10,
            "configurable": {
                **(request.extra_config or {})
            }
        }

        try:
            if request.thread_id:
                config['configurable'] = {
                    "thread_id": request.thread_id,
                    "user_id": request.user_id,
                    **(config['configurable'] or {})
                }

                with PostgresSaver.from_conn_string(os.getenv('DB_URI')) as checkpoint:
                    graph.checkpoint = checkpoint
            result = await graph.ainvoke(request, config)
            return result
        except Exception as e:
            print(traceback.format_exc())
            return None
