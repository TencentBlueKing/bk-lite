from src.core.state.basic_state import BasicState
from src.service.chatbot_workflow.entity.chatbot_workflow_request import ChatBotWorkflowRequest


class ChatBotWorkflowState(BasicState):
    graph_request: ChatBotWorkflowRequest