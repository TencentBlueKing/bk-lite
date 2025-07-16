from libs.metis.graph_core.state.basic_state import BasicState
from libs.metis.entity.agent.chatbot_workflow.chatbot_workflow_request import ChatBotWorkflowRequest


class ChatBotWorkflowState(BasicState):
    graph_request: ChatBotWorkflowRequest