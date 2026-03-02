import { CustomChatMessage } from '@/app/opspilot/types/global';

export interface Studio {
  id: number;
  name: string;
  introduction: string;
  created_by: string;
  team: string[];
  team_name: string[];
  online: boolean;
  is_pinned?: boolean;
  bot_type?: number;
  permissions?: string[];
  [key: string]: unknown;
}

export interface ModifyStudioModalProps {
  visible: boolean;
  onCancel: () => void;
  onConfirm: (values: Studio) => void;
  initialValues?: Studio | null;
}

export interface ChannelConfig {
  [key: string]: unknown;
}

export interface ChannelProps {
  id: string;
  name: string;
  enabled: boolean;
  icon: string;
  channel_config: ChannelConfig;
}

export interface LogRecord {
  key: string;
  title: string;
  createdTime: string;
  updatedTime: string;
  user: string;
  channel: string;
  count: number;
  ids?: number[];
  conversation?: CustomChatMessage[];
}

export interface WorkflowTaskResult {
  key: string;
  id: number;
  run_time: string;
  status: string;
  input_data: string;
  output_data: unknown;
  last_output: string;
  execute_type: string;
  bot_work_flow: number;
  execution_duration?: number;
  error_log?: string;
  execution_id?: string;
}

export interface ExecutionOutputParams {
  execution_id: string;
  id: number;
}

export interface ExecutionOutputData {
  [nodeId: string]: {
    name: string;
    type: string;
    index: number;
    input_data: unknown;
    output: unknown;
  };
}

export interface Channel {
  id: string;
  name: string;
}

// API Request/Response Types
export interface LogSearchParams {
  bot_id: string | number;
  start_time?: string;
  end_time?: string;
  search?: string;
  page?: number;
  page_size?: number;
  channel?: string;
}

export interface LogSearchResponse {
  items: LogRecord[];
  count: number;
}

export interface WorkflowTaskParams {
  bot_id: string | number;
  start_time?: string;
  end_time?: string;
  page?: number;
  page_size?: number;
}

export interface WorkflowTaskResponse {
  items: WorkflowTaskResult[];
  count: number;
}

export interface BotDetail extends Studio {
  llm_model?: number;
  rasa_model?: number;
  skill_ids?: number[];
  llm_skills?: number[];
  channels?: ChannelProps[];
  replica_count?: number;
  enable_bot_domain?: boolean;
  bot_domain?: string;
  enable_ssl?: boolean;
  enable_node_port?: boolean;
  node_port?: number;
  workflow_data?: {
    nodes?: unknown[];
    edges?: unknown[];
    [key: string]: unknown;
  };
}

export interface RasaModel {
  id: number;
  name: string;
  enabled: boolean;
}

export interface LlmModel {
  id: number;
  name: string;
  enabled: boolean;
  is_template?: boolean;
}

export interface BotConfigPayload {
  name?: string;
  introduction?: string;
  team?: string[];
  llm_model?: number;
  rasa_model?: number;
  skill_ids?: number[];
  [key: string]: unknown;
}

export interface TokenConsumptionParams {
  bot_id?: string | number;
  start_time?: string;
  end_time?: string;
}

export interface TokenConsumptionResponse {
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
}

export interface TokenOverviewParams {
  bot_id?: string | number;
  start_time?: string;
  end_time?: string;
  interval?: string;
}

export interface TokenOverviewItem {
  date: string;
  tokens: number;
}

export interface TokenOverviewResponse {
  items: TokenOverviewItem[];
}

export interface ConversationsParams {
  bot_id?: string | number;
  start_time?: string;
  end_time?: string;
  interval?: string;
}

export interface ConversationDataItem {
  date: string;
  count: number;
}

export interface ConversationsResponse {
  items: ConversationDataItem[];
}

export interface ActiveUsersParams {
  bot_id?: string | number;
  start_time?: string;
  end_time?: string;
  interval?: string;
}

export interface ActiveUsersItem {
  date: string;
  count: number;
}

export interface ActiveUsersResponse {
  items: ActiveUsersItem[];
}

export interface ExecuteWorkflowPayload {
  message?: string;
  bot_id: string;
  node_id: string;
}

export interface ExecuteWorkflowResponse {
  result: unknown;
  status: string;
}

export interface UserInfo {
  id: number;
  display_name: string;
  username: string;
}

export interface WorkflowLogParams {
  bot_id: string | number;
  entry_type?: string;
  start_time?: string;
  end_time?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export interface WorkflowLogItem {
  id: number;
  created_at: string;
  entry_type: string;
  input_data: string;
  output_data: unknown;
  status: string;
}

export interface WorkflowLogResponse {
  items: WorkflowLogItem[];
  count: number;
}

export interface WorkflowLogDetailParams {
  ids: number[];
  page?: number;
  page_size?: number;
}

export interface WorkflowLogDetail {
  id: number;
  node_name: string;
  input_data: unknown;
  output_data: unknown;
  status: string;
  execution_duration?: number;
}

export interface WorkflowLogDetailResponse {
  items: WorkflowLogDetail[];
  count: number;
}

export interface ChatApplicationParams {
  bot_id?: string | number;
  app_type?: string;
  page?: number;
  page_size?: number;
}

export interface ChatApplication {
  id: number;
  app_name: string;
  app_icon?: string;
  app_description?: string;
  bot: number;
  node_id: string;
  node_config?: {
    appIcon?: string;
    appDescription?: string;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export type ChatApplicationResponse = ChatApplication[];

export interface WebChatSession {
  id: string;
  session_id: string;
  title?: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface SessionMessage {
  id: string | number;
  conversation_role: string;
  conversation_content: string;
  conversation_time: string;
  role?: 'user' | 'bot';
  content?: string;
  created_at?: string;
}

export type SessionMessagesResponse = SessionMessage[];

export interface SkillGuideResponse {
  guide: string;
}

export interface InitialDataResponse {
  rasaModels: RasaModel[];
  llmModels: LlmModel[];
  channels: ChannelProps[];
  botDetail: BotDetail;
}
