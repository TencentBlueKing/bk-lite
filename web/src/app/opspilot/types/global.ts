import type { BrowserStepProgressData, BrowserStepsHistory, AgentStepProgressData } from '@bk-lite/chat-content/types';
export type { BrowserStepAction, BrowserStepProgressData, BrowserStepsHistory, AgentStepProgressData } from '@bk-lite/chat-content/types';
import type { ApprovalRequest, UserChoiceRequest, WikiCitation, SkillViewItem, ConfigDiffReport, ConfigAnalysisReport, ReportFileDownload, RepairCommands } from '@bk-lite/chat-content/types';
export type { ApprovalRequest, UserChoiceOption, UserChoiceRequest, WikiSearchExplanation, WikiCitation, SkillViewItem, ConfigDiffItem, A2UIAction, A2UIReportContract, ConfigDiffReport, ConfigAnalysisReportItem, ConfigAnalysisReportScope, ConfigAnalysisReportScanRange, ConfigAnalysisReportSummary, ConfigAnalysisSeveritySection, ConfigAnalysisRecommendation, ConfigAnalysisReport, ReportFileDownload, RepairCommands } from '@bk-lite/chat-content/types';




export interface BrowserTaskReceivedData {
  tool?: string;
  url?: string;
  task_final?: string;
  truncated?: boolean;
  timestamp_ms?: number;
  [key: string]: unknown;
}











/** DeepAgent planned_execution_step 分组后的对话展示数据 */
export interface PlannedExecutionStepView {
  step_index: number;
  total_steps: number;
  objective: string;
  status: 'running' | 'done' | 'failed' | 'skipped';
  toolCallIds: string[];
  reusedPriorResult?: boolean;
  error?: string;
}

export interface PlannedStepToolCallView {
  id: string;
  name: string;
  args: string;
  status: 'calling' | 'completed' | 'error';
  result?: string;
}



export interface CustomChatMessage {
  id: string;
  role: 'user' | 'bot';
  content: string;
  thinking?: string;
  isThinking?: boolean;
  createAt?: string;
  updateAt?: string;
  images?: Array<{
    id: string;
    url: string;
    name?: string;
    status?: 'uploading' | 'done' | 'error';
  }>;
  attachments?: Array<{
    id: number;
    name: string;
    mime: string;
    size: number;
    status: string;
    previewUrl?: string;
  }>;
  browserStepProgress?: BrowserStepProgressData | null;
  browserStepsHistory?: BrowserStepsHistory | null;
  approvalRequests?: ApprovalRequest[];
  userChoiceRequests?: UserChoiceRequest[];
  /** 点选确认卡时带上，手打的下一条消息没有这两项。 */
  choiceId?: string;
  choiceOption?: string;
  configDiffReports?: ConfigDiffReport[];
  configAnalysisReports?: ConfigAnalysisReport[];
  reportFileDownloads?: ReportFileDownload[];
  repairCommands?: RepairCommands[];
  agentStepProgress?: AgentStepProgressData[];
  plannedExecutionSteps?: PlannedExecutionStepView[];
  /** 规划阶段状态：planning/replanning 时展示「正在规划」反馈 */
  plannedExecutionStatus?: {
    phase: 'planning' | 'replanning' | 'planned' | 'idle' | string;
    step_count?: number;
    goal?: string;
    replan_count?: number;
    reason?: string;
  } | null;
  /** 与 plannedExecutionSteps 配套的工具快照；无步骤分组时也可用于历史回放 */
  toolCalls?: PlannedStepToolCallView[];
  /** 流式进行中为 true；结束后收起计划步骤 */
  isStreamingTools?: boolean;
  skillViews?: SkillViewItem[];
  wikiCitations?: WikiCitation[];
}



// Wiki 知识库引用:答案中对应的来源(知识页面/资料)。
// n/kb_id 仅智能体对话(按 [n] 标注)有;概览问答助手按标题引用,无 n。




























export interface ResultItem {
  id: number;
  name: string;
  content: string;
  created_at?: string;
  created_by?: string;
  knowledge_source_type: string;
  rerank_score?: number;
  score: number;
}
