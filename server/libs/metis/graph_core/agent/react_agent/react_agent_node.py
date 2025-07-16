from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from libs.metis.graph_core.node.tools_node import ToolsNodes


class ReActAgentNode(ToolsNodes):
    async def agent_node(self, state: TypedDict, config: RunnableConfig) -> TypedDict:
        messages = state["messages"]
        llm = self.get_llm_client(config["configurable"]["graph_request"])

        self.log(config, f"开始执行 agent_node 节点:输入消息数量: {len(state['messages'])}")

        agent_executor = create_react_agent(llm, self.tools,
                                            debug=False,
                                            prompt=config["configurable"]["graph_request"].system_message_prompt)

        agent_response = await agent_executor.ainvoke(
            {"messages": messages}
        )

        return {
            'messages': agent_response['messages'][-1],
        }
