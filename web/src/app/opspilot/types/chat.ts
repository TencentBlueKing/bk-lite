import {ReactNode} from 'react';
import {ButtonProps} from 'antd';
import {
  AgentStepProgressData,
  A2UIReportContract,
  BrowserStepAction,
  BrowserStepProgressData,
  BrowserTaskReceivedData,
  CustomChatMessage,
  SkillViewItem,
} from '@/app/opspilot/types/global';

export type { BrowserStepAction, BrowserStepProgressData };
export type { BrowserTaskReceivedData };
export type BrowserStepProgressValue = BrowserStepProgressData;
export type BrowserTaskReceivedValue = BrowserTaskReceivedData;
export type AgentStepProgressValue = AgentStepProgressData;
export interface SkillViewValue {
  items: SkillViewItem[];
}
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
  a2ui?: A2UIReportContract;
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
  a2ui?: A2UIReportContract;
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

export interface ConfigAnalysisReportItemValue {
  issue: string;
  count: number;
  workloads: string[];
  risk: string;
  [key: string]: unknown;
}

export interface ConfigAnalysisReportScopeValue {
  cluster_name?: string;
  namespace?: string | string[] | null;
  instance_name?: string | null;
  name?: string | null;
  target_name?: string | null;
  [key: string]: unknown;
}

export interface ConfigAnalysisReportScanRangeValue {
  offset?: number;
  limit?: number;
  has_more?: boolean;
  [key: string]: unknown;
}

export interface ConfigAnalysisReportSummaryValue {
  total?: number;
  problematic?: number;
  healthy?: number;
  top_recommendation?: string;
  [key: string]: unknown;
}

export interface ConfigAnalysisSeveritySectionValue {
  severity: 'critical' | 'high' | 'medium' | 'low' | 'warning' | 'info';
  title: string;
  issues: ConfigAnalysisReportItemValue[];
  items?: ConfigAnalysisReportItemValue[];
  [key: string]: unknown;
}

export interface ConfigAnalysisRecommendationValue {
  priority: 'P0' | 'P1' | 'P2' | 'P3';
  action: string;
  target: string;
  benefit: string;
  [key: string]: unknown;
}

export interface StructuredConfigAnalysisReportValue {
  report_id: string;
  title: string;
  cluster_name: string;
  a2ui?: A2UIReportContract;
  scope?: ConfigAnalysisReportScopeValue;
  scan_range?: ConfigAnalysisReportScanRangeValue;
  summary: ConfigAnalysisReportSummaryValue;
  severity_sections: ConfigAnalysisSeveritySectionValue[];
  recommendations: ConfigAnalysisRecommendationValue[];
  markdown: string;
  fallback_markdown?: string;
  [key: string]: unknown;
}

export interface MarkdownConfigAnalysisReportValue {
  report_id?: string;
  title?: string;
  cluster_name?: string;
  a2ui?: A2UIReportContract;
  scope?: ConfigAnalysisReportScopeValue;
  scan_range?: ConfigAnalysisReportScanRangeValue;
  summary?: ConfigAnalysisReportSummaryValue;
  severity_sections?: ConfigAnalysisSeveritySectionValue[];
  recommendations?: ConfigAnalysisRecommendationValue[];
  markdown: string;
  fallback_markdown?: string;
  [key: string]: unknown;
}

export type ConfigAnalysisReportValue =
  | StructuredConfigAnalysisReportValue
  | MarkdownConfigAnalysisReportValue;

export interface ReportFileDownloadValue {
  download_id: string;
  filename: string;
  content_base64?: string;
  mime_type: string;
  file_url?: string;
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
  value?: BrowserStepProgressValue | BrowserTaskReceivedValue | ApprovalRequestValue | UserChoiceRequestValue | AgentStepProgressValue | SubAgentProgressValue | SkillViewValue | ConfigAnalysisReportValue | Record<string, unknown>;
}

export interface GuideParseResult {
  text: string;
  items: string[];
  renderedHtml: string;
}
