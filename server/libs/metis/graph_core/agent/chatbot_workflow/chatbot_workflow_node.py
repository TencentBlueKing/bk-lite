from typing import TypedDict

from langchain_core.runnables import RunnableConfig

from libs.metis.graph_core.node.basic_node import BasicNode


class ChatBotWorkflowNode(BasicNode):
    def chatbot_node(self, state: TypedDict, config: RunnableConfig) -> TypedDict:
        request = config["configurable"]["graph_request"]

        # 记录节点执行前的信息
        self.log(config, f"开始执行 chatbot_node 节点:输入消息数量: {len(state['messages'])}")

        # 获取LLM客户端并调用
        llm = self.get_llm_client(request)

        result = llm.invoke(state["messages"])
        self.log(config, f"模型调用成功: {result.content}")

        return {
            'messages': result
        }
