import useApiClient from '@/utils/request';
import type {
  LogSearchParams,
  LogSearchResponse,
  WorkflowTaskParams,
  WorkflowTaskResponse,
  ChannelProps,
  BotDetail,
  RasaModel,
  LlmModel,
  BotConfigPayload,
  TokenConsumptionParams,
  TokenConsumptionResponse,
  TokenOverviewParams,
  TokenOverviewResponse,
  ConversationsParams,
  ConversationsResponse,
  ActiveUsersParams,
  ActiveUsersResponse,
  ExecuteWorkflowPayload,
  ExecuteWorkflowResponse,
  UserInfo,
  WorkflowLogParams,
  WorkflowLogResponse,
  WorkflowLogDetailParams,
  WorkflowLogDetailResponse,
  ChatApplicationParams,
  ChatApplicationResponse,
  WebChatSession,
  SessionMessagesResponse,
  SkillGuideResponse,
} from '@/app/opspilot/types/studio';

export const useStudioApi = () => {
  const { get, post, del, patch } = useApiClient();

  const fetchLogs = async (params: LogSearchParams): Promise<LogSearchResponse> => {
    return get('/opspilot/bot_mgmt/history/search_log/', { params });
  };

  const fetchWorkflowTaskResult = async (params: WorkflowTaskParams): Promise<WorkflowTaskResponse> => {
    return get('/opspilot/bot_mgmt/workflow_task_result/', { params });
  };

  const fetchChannels = async (botId: string | null): Promise<ChannelProps[]> => {
    return get('/opspilot/bot_mgmt/bot/get_bot_channels/', { params: { bot_id: botId } });
  };

  const fetchBotDetail = async (botId: string | null): Promise<BotDetail> => {
    return get(`/opspilot/bot_mgmt/bot/${botId}/`);
  };

  const updateChannel = async (config: ChannelProps): Promise<void> => {
    return post('/opspilot/bot_mgmt/bot/update_bot_channel/', config);
  };

  const deleteStudio = async (studioId: number): Promise<void> => {
    return del(`/opspilot/bot_mgmt/bot/${studioId}/`);
  };

  const toggleBotPin = async (botId: number): Promise<void> => {
    return post(`/opspilot/bot_mgmt/bot/${botId}/toggle_pin/`);
  };

  const fetchInitialData = async (botId: string | null): Promise<[RasaModel[], LlmModel[], ChannelProps[], BotDetail]> => {
    const [rasaModelsData, skillsResponse, channelsData, botData] = await Promise.all([
      get<RasaModel[]>('/opspilot/bot_mgmt/rasa_model/'),
      get<LlmModel[]>('/opspilot/model_provider_mgmt/llm/'),
      get<ChannelProps[]>('/opspilot/bot_mgmt/bot/get_bot_channels/', { params: { bot_id: botId } }),
      get<BotDetail>(`/opspilot/bot_mgmt/bot/${botId}`)
    ]);

    const skillsData = skillsResponse.filter((skill) => !skill.is_template);

    return [rasaModelsData, skillsData, channelsData, botData];
  };

  const saveBotConfig = async (botId: string | null, payload: BotConfigPayload): Promise<void> => {
    return patch(`/opspilot/bot_mgmt/bot/${botId}/`, payload);
  };

  const toggleOnlineStatus = async (botId: string | null): Promise<void> => {
    return post('/opspilot/bot_mgmt/bot/stop_pilot/', { bot_ids: [Number(botId)] });
  };

  const fetchTokenConsumption = async (params: TokenConsumptionParams): Promise<TokenConsumptionResponse> => {
    return get('/opspilot/bot_mgmt/get_total_token_consumption/', { params });
  };

  const fetchTokenOverview = async (params: TokenOverviewParams): Promise<TokenOverviewResponse> => {
    return get('/opspilot/bot_mgmt/get_token_consumption_overview/', { params });
  };

  const fetchConversations = async (params: ConversationsParams): Promise<ConversationsResponse> => {
    return get('/opspilot/bot_mgmt/get_conversations_line_data/', { params });
  };

  const fetchActiveUsers = async (params: ActiveUsersParams): Promise<ActiveUsersResponse> => {
    return get('/opspilot/bot_mgmt/get_active_users_line_data/', { params });
  };

  const executeWorkflow = async (payload: ExecuteWorkflowPayload): Promise<ExecuteWorkflowResponse> => {
    return post(`/opspilot/bot_mgmt/execute_chat_flow/${payload.bot_id}/${payload.node_id}`, { message: payload.message, is_test: true });
  };

  const getExecuteWorkflowSSEUrl = (botId: string, nodeId: string): string => {
    return `/api/proxy/opspilot/bot_mgmt/execute_chat_flow/${botId}/${nodeId}`;
  };

  const getAllUsers = async (): Promise<UserInfo[]> => {
    return get('/system_mgmt/user/user_id_all/');
  };

  const fetchWorkflowLogs = async (params: WorkflowLogParams): Promise<WorkflowLogResponse> => {
    return get('/opspilot/bot_mgmt/bot/search_workflow_log/', { params });
  };

  const fetchWorkflowLogDetail = async (params: WorkflowLogDetailParams): Promise<WorkflowLogDetailResponse> => {
    return post('/opspilot/bot_mgmt/bot/get_workflow_log_detail/', params);
  };

  const fetchApplication = async (params: ChatApplicationParams): Promise<ChatApplicationResponse> => {
    return get('/opspilot/bot_mgmt/chat_application/', { params });
  };

  const fetchWebChatSessions = async (botId: string | number, nodeId?: string | number): Promise<WebChatSession[]> => {
    return get('/opspilot/bot_mgmt/chat_application/web_chat_sessions/', { params: { bot_id: botId, node_id: nodeId } });
  };

  const fetchSessionMessages = async (sessionId: string): Promise<SessionMessagesResponse> => {
    return get('/opspilot/bot_mgmt/chat_application/session_messages/', { params: { session_id: sessionId } });
  };

  const fetchSkillGuide = async (botId: string, nodeId: string): Promise<SkillGuideResponse> => {
    return get('/opspilot/bot_mgmt/chat_application/skill_guide/', { params: { bot_id: botId, node_id: nodeId } });
  };

  const deleteSessionHistory = async (nodeId: string | number, sessionId: string): Promise<void> => {
    return post('/opspilot/bot_mgmt/chat_application/delete_session_history/', { node_id: nodeId, session_id: sessionId });
  };

  return {
    fetchLogs,
    fetchWorkflowTaskResult,
    fetchChannels,
    fetchBotDetail,
    updateChannel,
    deleteStudio,
    toggleBotPin,
    fetchInitialData,
    saveBotConfig,
    toggleOnlineStatus,
    fetchTokenConsumption,
    fetchTokenOverview,
    fetchConversations,
    fetchActiveUsers,
    executeWorkflow,
    getExecuteWorkflowSSEUrl,
    getAllUsers,
    fetchWorkflowLogs,
    fetchWorkflowLogDetail,
    fetchWebChatSessions,
    fetchApplication,
    fetchSessionMessages,
    fetchSkillGuide,
    deleteSessionHistory,
  };
};
