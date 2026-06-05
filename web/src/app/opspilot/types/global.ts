export interface KnowledgeItem {
  score: number;
  content: string;
}

export interface KnowledgeBase {
  citing_num: number;
  knowledge_id: number;
  knowledge_base_id: number;
  knowledge_source_type: string;
  knowledge_title: string;
  result: KnowledgeItem[]
}

export interface Annotation {
  answer: CustomChatMessage;
  question: CustomChatMessage;
  selectedKnowledgeBase: string | number;
  tagId?: number | string;
}

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

export interface CustomChatMessage {
  id: string;
  role: 'user' | 'bot';
  content: string;
  thinking?: string;
  isThinking?: boolean;
  createAt?: string;
  updateAt?: string;
  knowledgeBase?: KnowledgeBase | null;
  annotation?: Annotation | null;
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

export interface ConfigDiffReport {
  report_id: string;
  title: string;
  cluster_name: string;
  items: ConfigDiffItem[];
  received_at: number;
}

export interface ConfigAnalysisReportItem {
  issue: string;
  count: number;
  workloads: string[];
  risk: string;
}

export interface ConfigAnalysisSeveritySection {
  severity: 'critical' | 'high' | 'medium' | 'low' | 'warning' | 'info';
  title: string;
  items: ConfigAnalysisReportItem[];
}

export interface ConfigAnalysisRecommendation {
  priority: 'P1' | 'P2' | 'P3';
  action: string;
  target: string;
  benefit: string;
}

export interface ConfigAnalysisReport {
  report_id: string;
  title: string;
  cluster_name: string;
  summary: {
    total?: number;
    problematic?: number;
    healthy?: number;
    top_recommendation?: string;
  };
  severity_sections: ConfigAnalysisSeveritySection[];
  recommendations: ConfigAnalysisRecommendation[];
  fallback_markdown: string;
  received_at: number;
}

export interface ReportFileDownload {
  download_id: string;
  filename: string;
  content_base64: string;
  mime_type: string;
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
