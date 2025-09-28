from src.core.llm.state.basic_state import BasicState
from src.web.entity.agent.chatbot_workflow.chatbot_workflow_request import ChatBotWorkflowRequest


class ChatBotWorkflowState(BasicState):
    graph_request: ChatBotWorkflowRequest