import {ReactNode} from 'react';
import {ButtonProps} from 'antd';
import {
  AgentStepProgressData,
  Annotation,
  BrowserStepAction,
  BrowserStepProgressData,
  BrowserTaskReceivedData,
  CustomChatMessage
} from '@/app/opspilot/types/global';

export type { BrowserStepAction, BrowserStepProgressData };
export type { BrowserTaskReceivedData };
export type BrowserStepProgressValue = BrowserStepProgressData;
export type BrowserTaskReceivedValue = BrowserTaskReceivedData;
export type AgentStepProgressValue = AgentStepProgressData;
export interface SubAgentProgressValue {
  agent_name: string;
  status: 'started' | 'completed' | 'error' | 'parallel_started' | 'parallel_completed';
  description: string;
  agents?: string[];
}

export interface ApprovalRequestValue {
  execution_id: string;
  node_id: string;
  tool_call_id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  timeout_seconds: number;
}

export interface UserChoiceRequestValue {
  execution_id: string;
  node_id: string;
  choice_id: string;
  title: string;
  description?: string;
  options: Array<{
    key: string;
    label: string;
    description?: string;
    icon?: string;
    disabled?: boolean;
    recommended?: boolean;
  }>;
  multiple: boolean;
  min_select: number;
  max_select: number;
  timeout_seconds: number;
  default_keys: string[];
  display_hint: 'auto' | 'buttons' | 'dropdown' | 'checkbox';
}

export interface ConfigDiffReportValue {
  report_id: string;
  title: string;
  cluster_name: string;
  items: Array<{
    workload_name: string;
    workload_type: string;
    namespace: string;
    severity: 'critical' | 'high' | 'warning' | 'info';
    summary: string;
    before_yaml: string;
    after_yaml: string;
  }>;
}

export interface ConfigAnalysisReportValue {
  report_id: string;
  markdown: string;
}

export interface ReportFileDownloadValue {
  download_id: string;
  filename: string;
  content_base64: string;
  mime_type: string;
}

export interface ReportFileDownload extends ReportFileDownloadValue {
  received_at: number;
}

export interface RepairCommandsValue {
  commands_id: string;
  commands_markdown: string;
}

export interface RepairCommands extends RepairCommandsValue {
  received_at: number;
}

export interface CustomChatSSEProps {
  handleSendMessage?: (message: string, currentMessages?: any[]) => Promise<{
    url: string;
    payload: any;
    interruptRequest?: {
      enabled: boolean;
      url: string;
      reason?: string;
    };
  } | null>;
  showMarkOnly?: boolean;
  initialMessages?: CustomChatMessage[];
  mode?: 'chat' | 'display';
  guide?: string;
  useAGUIProtocol?: boolean;
  showHeader?: boolean;
  requirePermission?: boolean;
  removePendingBotMessageOnCancel?: boolean;
}

export type ActionRender = (
  _: any,
  info: {
    components: {
      SendButton: React.ComponentType<ButtonProps>;
      LoadingButton: React.ComponentType<ButtonProps>;
    };
  }
) => ReactNode;

export interface SSEChunk {
  choices: Array<{
    delta: {
      content?: string;
    };
    index: number;
    finish_reason: string | null;
  }>;
  id: string;
  object: string;
  created: number;
}

export interface AGUIMessage {
  type: 'RUN_STARTED' | 'THINKING' | 'TEXT_MESSAGE_START' | 'TEXT_MESSAGE_CONTENT' | 'TEXT_MESSAGE_END' | 'RUN_FINISHED' | 'TOOL_CALL_START' | 'TOOL_CALL_ARGS' | 'TOOL_CALL_END' | 'TOOL_CALL_RESULT' | 'ERROR' | 'RUN_ERROR' | 'CUSTOM';
  timestamp: number;
  threadId?: string;
  runId?: string;
  messageId?: string;
  role?: string;
  delta?: string;
  toolCallId?: string;
  toolCallName?: string;
  parentMessageId?: string;
  content?: string;
  error?: string;
  message?: string;
  code?: string;
  name?: string;
  value?: BrowserStepProgressValue | BrowserTaskReceivedValue | ApprovalRequestValue | UserChoiceRequestValue | AgentStepProgressValue | SubAgentProgressValue | ConfigAnalysisReportValue | Record<string, unknown>;
}

export interface ReferenceModalState {
  visible: boolean;
  loading: boolean;
  title: string;
  content: string;
}

export interface DrawerContentState {
  visible: boolean;
  title: string;
  content: string;
  chunkType?: "Document" | "QA" | "Graph";
  graphData?: { nodes: any[], edges: any[] };
}

export interface GuideParseResult {
  text: string;
  items: string[];
  renderedHtml: string;
}

export interface ReferenceParams {
  refNumber: string;
  chunkId: string | null;
  knowledgeId: string | null;
}

export interface MessageActionsProps {
  message: CustomChatMessage;
  onCopy: (content: string) => void;
  onRegenerate: (id: string) => void;
  onDelete: (id: string) => void;
  onMark: (message: CustomChatMessage) => void;
  showMarkOnly?: boolean;
}

export interface AnnotationModalProps {
  visible: boolean;
  showMarkOnly?: boolean;
  annotation: Annotation | null;
  onSave: (annotation?: Annotation) => void;
  onRemove: (id: string | undefined) => void;
  onCancel: () => void;
}
