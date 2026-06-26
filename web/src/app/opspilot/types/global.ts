export interface BrowserStepAction {
  navigate?: { url: string; new_tab?: boolean };
  wait?: { seconds: number };
  input?: { index: number; text: string; clear?: boolean };
  click?: { index: number };
  scroll?: { direction?: 'up' | 'down'; amount?: number };
  screenshot?: boolean;
  [key: string]: unknown;
}

export interface BrowserStepProgressData {
  step_number: number;
  max_steps: number;
  url: string;
  title: string;
  thinking: string;
  evaluation: string;
  memory: string;
  next_goal: string;
  actions: BrowserStepAction[];
  has_screenshot: boolean;
  screenshot?: string;
}

export interface BrowserTaskReceivedData {
  tool?: string;
  url?: string;
  task_final?: string;
  truncated?: boolean;
  timestamp_ms?: number;
  [key: string]: unknown;
}

export interface BrowserStepsHistory {
  steps: BrowserStepProgressData[];
  isRunning: boolean;
}

export interface ApprovalRequest {
  execution_id: string;
  node_id: string;
  tool_call_id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  timeout_seconds: number;
  received_at: number;
  status: 'pending' | 'approved' | 'rejected';
}

export interface UserChoiceOption {
  key: string;
  label: string;
  description?: string;
  icon?: string;
  disabled?: boolean;
  recommended?: boolean;
}

export interface UserChoiceRequest {
  execution_id: string;
  node_id: string;
  choice_id: string;
  a2ui?: A2UIReportContract;
  title: string;
  description?: string;
  options: UserChoiceOption[];
  multiple: boolean;
  min_select: number;
  max_select: number;
  timeout_seconds: number;
  default_keys: string[];
  display_hint: 'auto' | 'buttons' | 'dropdown' | 'checkbox' | 'text';
  received_at: number;
  status: 'pending' | 'submitted' | 'timeout';
  selected?: string[];
}

export interface AgentStepProgressData {
  agent_name?: string;
  step: number;
  max_steps: number;
  status: 'started' | 'running' | 'completed' | 'error' | 'parallel_started' | 'parallel_completed';
  description: string;
  tool_name?: string;
  elapsed_seconds?: number;
  total_elapsed_seconds?: number;
}

export interface SkillViewItem {
  id: string;
  name: string;
  package_id?: string;
  description?: string;
  missing_tools?: string[];
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
  browserStepProgress?: BrowserStepProgressData | null;
  browserStepsHistory?: BrowserStepsHistory | null;
  approvalRequests?: ApprovalRequest[];
  userChoiceRequests?: UserChoiceRequest[];
  configDiffReports?: ConfigDiffReport[];
  configAnalysisReports?: ConfigAnalysisReport[];
  reportFileDownloads?: ReportFileDownload[];
  repairCommands?: RepairCommands[];
  agentStepProgress?: AgentStepProgressData[];
  skillViews?: SkillViewItem[];
  wikiCitations?: WikiCitation[];
}

// Wiki 知识库引用:答案中对应的来源(知识页面/资料)。
// n/kb_id 仅智能体对话(按 [n] 标注)有;概览问答助手按标题引用,无 n。
export interface WikiCitation {
  n?: number;
  kb_id?: number;
  kind: string; // page | material_summary
  id: number;
  title: string;
}

export interface ConfigDiffItem {
  workload_name: string;
  workload_type: string;
  namespace: string;
  severity: 'critical' | 'high' | 'warning' | 'info';
  summary: string;
  before_yaml: string;
  after_yaml: string;
}

export interface A2UIAction {
  key: string;
  label: string;
  [key: string]: unknown;
}

export interface A2UIReportContract {
  version: string;
  component: 'config-analysis-report' | 'config-diff-report' | string;
  event_name: string;
  render_mode: 'card' | string;
  actions: A2UIAction[];
  [key: string]: unknown;
}

export interface ConfigDiffReport {
  report_id: string;
  title: string;
  cluster_name: string;
  a2ui?: A2UIReportContract;
  items: ConfigDiffItem[];
  received_at: number;
}

export interface ConfigAnalysisReportItem {
  issue: string;
  count: number;
  workloads: string[];
  risk: string;
  [key: string]: unknown;
}

export interface ConfigAnalysisReportScope {
  cluster_name?: string;
  namespace?: string | null;
  instance_name?: string | null;
  name?: string | null;
  target_name?: string | null;
  [key: string]: unknown;
}

export interface ConfigAnalysisReportScanRange {
  offset?: number;
  limit?: number;
  has_more?: boolean;
  [key: string]: unknown;
}

export interface ConfigAnalysisReportSummary {
  total?: number;
  problematic?: number;
  healthy?: number;
  top_recommendation?: string;
  [key: string]: unknown;
}

export interface ConfigAnalysisSeveritySection {
  severity: 'critical' | 'high' | 'medium' | 'low' | 'warning' | 'info';
  title: string;
  issues: ConfigAnalysisReportItem[];
  items?: ConfigAnalysisReportItem[];
  [key: string]: unknown;
}

export interface ConfigAnalysisRecommendation {
  priority: 'P0' | 'P1' | 'P2' | 'P3';
  action: string;
  target: string;
  benefit: string;
  [key: string]: unknown;
}

export interface ConfigAnalysisReport {
  report_id: string;
  title: string;
  cluster_name: string;
  a2ui?: A2UIReportContract;
  scope?: ConfigAnalysisReportScope;
  scan_range?: ConfigAnalysisReportScanRange;
  summary: ConfigAnalysisReportSummary;
  severity_sections: ConfigAnalysisSeveritySection[];
  recommendations: ConfigAnalysisRecommendation[];
  markdown: string;
  fallback_markdown: string;
  received_at: number;
  [key: string]: unknown;
}

export interface ReportFileDownload {
  download_id: string;
  filename: string;
  content_base64?: string;
  mime_type: string;
  file_url?: string;
  received_at: number;
}

export interface RepairCommands {
  commands_id: string;
  commands_markdown: string;
  received_at: number;
}

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
