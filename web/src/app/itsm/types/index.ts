export interface FieldFetchBinding {
  source: 'integration' | 'dictionary' | 'table';
  mode: 'options' | 'value' | 'table';
  integration_id?: number;
  integration_kind?: 'api' | 'python';
  resource_key?: string;
  inputs?: Record<string, unknown>;
  dependencies?: string[];
  list_path?: string;
  label_path?: string;
  value_path?: string;
  columns?: Record<string, string>;
  fill?: Record<string, string>;
  transform_id?: number;
  transform_params?: Record<string, unknown>;
  trigger?: 'change' | 'manual';
  enforce?: boolean;
}

export interface FormChoice {
  label: string;
  value: string | number;
  children?: FormChoice[];
}

export interface FormFieldSchema {
  key: string;
  type: string;
  label: string;
  required?: boolean;
  default?: unknown;
  props?: Record<string, unknown>;
  fetch?: FieldFetchBinding;
  source?: { type: string; options?: FormChoice[] };
  placeholder?: string;
  hint?: string;
  span?: number;
  rowBreak?: boolean;
  group?: string;
  visibleWhen?: ConditionGroup | ConditionItem | null;
  state?: 'default' | 'disabled' | 'readonly' | 'hidden';
  hideValueClearMode?: 'keep' | 'clear';
  hideLogic?: 'visible' | 'always';
  cascadeAnyLevel?: boolean;
  showCascadePath?: boolean;
  children?: FormFieldSchema[];
  optionLayout?: 'horizontal' | 'vertical';
  rows?: number;
}

export interface FormSchema {
  version: number;
  fields: FormFieldSchema[];
  layout?: Record<string, unknown>[];
  rules?: { type: 'required' | 'visible' | 'compute'; field: string; when?: ConditionGroup | ConditionItem | null; expr?: string }[];
}

export interface ConditionItem {
  field: string;
  op: string;
  value?: unknown;
}

export interface ConditionGroup {
  logic: 'and' | 'or';
  items: Array<ConditionItem | ConditionGroup>;
}

export interface FlowNodeData {
  label: string;
  nodeType: string;
}

export interface PortalService {
  id: number;
  name: string;
  catalog_id: number | null;
  workflow_id: number;
  workflow_name?: string;
  version_id: number | null;
  description: string;
  is_hot: boolean;
  is_enabled: boolean;
}

export interface PortalCatalog {
  id: number;
  name: string;
  parent_id: number | null;
}

export interface PortalData {
  service_total?: number;
  can_manage?: boolean;
  can_apply?: boolean;
  catalogs: PortalCatalog[];
  services: PortalService[];
  favorites: PortalService[];
  recents: PortalService[];
  hots: PortalService[];
}

export interface NamedItem {
  id: number;
  name: string;
  key: string;
}

export interface HandoverDraft {
  from_user: string;
  to_user: string;
  ticket_ids: number[];
  opinion?: string;
}

export type HandoverResultStatus = 'pending' | 'succeeded' | 'failed' | 'skipped' | 'unconfirmed';

export interface HandoverResult {
  ticket_id: number;
  task_id: number | null;
  status: HandoverResultStatus;
  message: string;
}

export interface HandoverRecord extends HandoverDraft {
  id: number;
  created_at: string;
  results?: HandoverResult[];
}

export interface HandoverCandidate {
  id: number;
  sn: string;
  title: string;
  requires_opinion?: boolean;
}

export interface WorkflowListItem extends NamedItem {
  published_version_no?: number | null;
  current_version_no?: number | null;
  form_id: number | null;
  current_version_id: number | null;
}

export interface TicketReturnTarget {
  node_id: string;
  name: string;
  completed_at: string;
}

export interface NodeActionDisplay {
  action: string;
  label?: string;
}

export interface TicketTaskItem {
  allowed_actions?: string[];
  action_display?: NodeActionDisplay[];
  required_opinion_actions?: string[];
  return_targets?: TicketReturnTarget[];
  id: number;
  node_id: string;
  node_name: string;
  node_type?: string;
  can_operate?: boolean;
  field_perm?: Record<string, 'hidden' | 'read' | 'edit'>;
  assignee: string;
  status: string;
}

export interface TicketListItem {
  created_at?: string;
  updated_at?: string;
  workflow?: string;
  priority?: string;
  id: number;
  sn: string;
  title: string;
  status: string;
  creator: string;
  tasks: TicketTaskItem[];
  sla_target?: string;
  sla_due_at?: string;
  sla_breached?: boolean;
}

export interface TicketLogItem {
  action: string;
  operator: string;
  message: string;
}

export interface TicketJobProgress {
  dispatch_mode?: 'batch' | 'parallel';
  mode: 'once' | 'each';
  total?: number;
  batch_size?: number;
}

export interface TicketJobRecord {
  row: number;
  job_id: number;
  status?: string;
}

export interface TicketProgressNode {
  job_progress?: TicketJobProgress;
  job_records?: TicketJobRecord[];
  executing?: boolean;
  outcome?: 'waiting' | 'current' | 'passed' | 'accepted' | 'rejected' | 'failed';
  id: string;
  name: string;
  type: string;
  state: 'done' | 'current' | 'waiting' | 'failed';
  assignees?: string[];
  started_at?: string;
  finished_at?: string;
}

export interface TicketProgressEdge {
  from: string;
  to: string;
  default?: boolean;
}

export interface TicketSLAItem {
  target: string;
  due_at: string;
  warning_at?: string;
  finished_at: string;
  breached: boolean;
  paused: boolean;
  notices?: TicketSLANotice[];
}

export interface TicketSLANotice {
  id: number;
  kind: 'warning' | 'escalation';
  triggered_at: string;
  status: 'sent' | 'failed' | 'skipped';
  recipients: string[];
  message: string;
}

export interface AutoExecutionReview {
  review_token: string;
  outcome: 'executed' | 'not_executed';
  note: string;
  result_value?: unknown;
}

export interface TicketHistoryItem {
  job_progress?: TicketJobProgress;
  job_records?: TicketJobRecord[];
  executing?: boolean;
  id: string;
  node_id: string;
  name: string;
  action_label: string;
  action?: string;
  operator: string;
  state: string;
  started_at: string;
  finished_at: string;
  message: string;
  opinion?: string;
  execution_id?: number;
  can_retry?: boolean;
  review_token?: string;
  result_field?: string | null;
  job_id?: string;
}

export interface TicketAttachmentItem {
  id: number;
  name: string;
  size: number;
  operator: string;
  created_at: string;
  comment_id?: number;
  can_delete: boolean;
}

export interface TicketCommentItem {
  id: number;
  operator: string;
  content: string;
  parent_id?: number;
  created_at: string;
  attachment_ids: number[];
}

export interface SurveyQuestion {
  id: string;
  title: string;
  required: boolean;
}

export interface SurveyTemplateSnapshot {
  name: string;
  questions: SurveyQuestion[];
}

export interface SurveySubmission {
  score: number;
  comment?: string;
  answers?: Record<string, string>;
}

export interface SurveyResult {
  score: number;
  comment: string;
  answers?: Array<{ id: string; title: string; value: string }>;
}

export interface ManualRecoveryDecision { decision: 'abandon'; token: string; sent_at: string; verified: true; reason: string }
export type StartRecoveryRequest = { id: number; action: 'check' } | { id: number; action: 'confirmed_not_started'; sent_at: string; reason: string };

export interface TicketDetail {
  can_rename?: boolean;
  reopen_from?: string | null;
  engine_pending?: boolean;
  manual_recovery?: { action: string; status: string; can_check: boolean; can_abandon?: boolean; token?: string; sent_at?: string | null } | null;
  start_recovery?: { id: number; kind: 'initial' | 'reopen'; state: string; business_key: string; sent_at: string | null; can_confirm: boolean } | null;
  selected_task_id?: number | null;
  form_rules?: FormSchema['rules'];
  history?: TicketHistoryItem[];
  created_at?: string;
  workflow_name?: string;
  allowed_actions?: string[];
  action_display?: NodeActionDisplay[];
  required_opinion_actions?: string[];
  can_survey?: boolean;
  id: number;
  sn: string;
  title: string;
  status: string;
  creator: string;
  form_data: Record<string, unknown>;
  fields: FormFieldSchema[];
  stages?: Array<{ key: string; name: string; state: 'done' | 'current' | 'waiting' }>;
  tasks: TicketTaskItem[];
  nodes: TicketProgressNode[];
  edges?: TicketProgressEdge[];
  logs: TicketLogItem[];
  sla?: TicketSLAItem[];
  survey?: SurveyResult | null;
  survey_template?: SurveyTemplateSnapshot | null;
}

export type TicketFormOperator = 'contains' | 'eq' | 'gte' | 'lte';
export interface TicketFormCondition {
  key: string;
  operator: TicketFormOperator;
  value: string | number | null;
}

export interface TicketCenterFilters {
  q: string;
  status: string;
  creator: string;
  priority: string;
  tag: string;
  created_after: string;
  created_before: string;
  tab: string;
  ordering: string;
  workflow_id: string;
  form_filters: TicketFormCondition[];
}

export interface TicketFilterWorkflow { id: number; name: string }
export interface TicketFilterField {
  key: string;
  label: string;
  type: 'input' | 'textarea' | 'number' | 'date' | 'radio' | 'select';
  options: { label: string; value: string | number }[];
}

export interface TicketExportRecord {
  id: number;
  status: 'pending' | 'running' | 'done' | 'failed';
  filename: string;
  created_at: string;
  finished_at: string | null;
  count: number;
  downloadable: boolean;
  error: string;
}

export interface TicketExportColumn {
  key: string;
  label: string;
}

export interface TicketExportCatalog {
  groups: { key: string; label: string; columns: TicketExportColumn[] }[];
  default_columns: string[];
  workflows?: TicketFilterWorkflow[];
  workflow?: TicketFilterWorkflow;
  fields?: (TicketExportColumn & { type: string })[];
}
