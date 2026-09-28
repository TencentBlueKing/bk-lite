export type WorkflowStatus = 'DRAFT' | 'PUBLISHED';
export type ExecutionStatus = 'QUEUED' | 'RUNNING' | 'WAITING_APPROVAL' | 'TERMINATING' | 'SUCCEEDED' | 'FAILED' | 'TIMED_OUT' | 'TERMINATED';
export type WorkflowTriggerType = 'FORM' | 'SCHEDULE' | 'WEBHOOK' | 'NATS';

export interface PaginatedResponse<T> {
  count: number;
  items: T[];
}

export interface WorkflowDashboard {
  kpis: {
    workflow_total: number;
    published_workflows: number;
    enabled_workflows: number;
    draft_workflows: number;
    today_executions: number;
    success_rate: number | null;
    running_executions: number;
    queued_executions: number;
    failed_executions: number;
    pending_approvals: number;
  };
  trend: WorkflowDashboardTrendPoint[];
  status_distribution: WorkflowDashboardStatusCount[];
  recent_executions: ExecutionRecord[];
  pending_approvals: WorkflowDashboardApproval[];
}

export interface WorkflowDashboardTrendPoint {
  date: string;
  total: number;
  succeeded: number;
  failed: number;
  timed_out: number;
  other: number;
}

export interface WorkflowDashboardStatusCount {
  status: ExecutionStatus;
  label: string;
  count: number;
}

export interface WorkflowDashboardApproval {
  id: string;
  execution: string;
  workflow_name: string;
  workflow_version: number;
  execution_started_by: string;
  task_reference: string;
  title: string;
  due_at: string | null;
  created_at: string;
}

export interface ConductorTask {
  name: string;
  taskReferenceName: string;
  type: 'SIMPLE' | 'FORK_JOIN' | 'JOIN' | 'SWITCH' | 'HUMAN';
  inputParameters?: Record<string, unknown>;
  forkTasks?: ConductorTask[][];
  joinOn?: string[];
  decisionCases?: Record<string, ConductorTask[]>;
  defaultCase?: ConductorTask[];
  evaluatorType?: 'value-param' | 'javascript';
  expression?: string;
}

export interface ConductorDefinition {
  name: string;
  description?: string;
  version: number;
  schemaVersion: number;
  ownerEmail?: string;
  inputParameters?: string[];
  outputParameters?: Record<string, unknown>;
  variables?: Record<string, unknown>;
  tasks: ConductorTask[];
  restartable?: boolean;
  workflowStatusListenerEnabled?: boolean;
}

export interface WorkflowRecord {
  id: number;
  name: string;
  description: string;
  status: WorkflowStatus;
  current_version: number;
  enabled: boolean;
  has_draft: boolean;
  draft_revision: number;
  draft_base_version: number;
  definition: ConductorDefinition;
  canvas_metadata: Record<string, unknown>;
  engine_name: string;
  trigger_summary?: WorkflowTriggerType[];
  recent_execution_status?: ExecutionStatus | null;
  recent_execution_at?: string | null;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  permission?: string[];
}

export interface NodeTarget {
  id: string;
  source: 'node_mgmt' | 'job_mgmt';
  source_id: string | number;
  name: string;
  ip: string;
  operating_system: 'linux' | 'windows';
  cpu_architecture?: string;
  cloud_region_id?: string | number | null;
  connected?: boolean | null;
  organization_ids?: number[];
}

export type TargetSource = NodeTarget['source'];

export interface WorkflowTargetField {
  key: string;
  name: string;
  required: boolean;
  binding_mode: 'runtime';
  allowed_sources: TargetSource[];
  allowed_operating_systems?: Array<'linux' | 'windows'>;
  min_count: number;
  max_count: number;
}

export type FormFieldWidget = 'input' | 'textarea' | 'code' | 'number' | 'switch' | 'select' | 'radio' | 'multiselect' | 'tags' | 'key-value' | 'json' | 'target-selector' | 'file-upload' | 'agent-knowledge-upload';

export interface TargetFieldBinding {
  mode: 'runtime';
  allowedSources: TargetSource[];
  allowedOperatingSystems: Array<'linux' | 'windows'>;
  minCount: number;
  maxCount: number;
}

export interface FileFieldOptions {
  accept: Array<'docx' | 'xlsx'>;
  maxSizeMiB: number;
  maxCount: 1;
  sourceModes: Array<'upload'>;
  sampleFiles?: Array<{ name: string; url: string }>;
}

export interface WorkflowLaunchPlan {
  workflow_id: number;
  workflow_name: string;
  workflow_version: number;
  input_schema: JsonSchema;
  ui_schema: Record<string, unknown>;
  target_fields: WorkflowTargetField[];
  risk_summary: { level?: string; description?: string };
  parent_execution_id?: string | null;
  launch_token: string;
  expires_in_seconds: number;
}

export interface TargetListResponse {
  source: TargetSource;
  count: number;
  items: NodeTarget[];
}

export interface TargetMatchItem {
  value: string;
  status: 'matched' | 'unauthorized' | 'not_found' | 'duplicate' | 'ambiguous';
  targets: NodeTarget[];
}

export interface TargetMatchResponse {
  source: TargetSource;
  results: TargetMatchItem[];
}

export interface WorkflowTargetSnapshotField {
  items: NodeTarget[];
  count: number;
  offline_count: number;
  source_counts: Record<TargetSource, number>;
  operating_system_counts: Record<'linux' | 'windows', number>;
}

export interface WorkflowTargetSnapshot {
  fields?: Record<string, WorkflowTargetSnapshotField>;
  unique_total?: number;
  offline_count?: number;
  offline_confirmed?: boolean;
}

export interface AtomCatalogItem {
  key: string;
  name: string;
  category: string;
  description: string;
  input_schema?: JsonSchema;
  output_schema?: JsonSchema;
  ui_schema?: Record<string, unknown>;
  built_in?: boolean;
  default_timeout_seconds?: number;
  retry_count?: number;
  retry_delay_seconds?: number;
  idempotent?: boolean;
  safety_level?: 'READ_ONLY' | 'MUTATION';
  resource_scope?: 'ORGANIZATION' | 'NODE_INPUT';
}

export interface AtomDefinitionRecord {
  key: string;
  name: string;
  category: string;
  node_type: 'TRIGGER' | 'ACTION' | 'CONTROL' | 'RETURN';
  description: string;
  source_type: 'SYSTEM' | 'PLATFORM' | 'PACKAGE';
  input_schema: JsonSchema;
  output_schema: JsonSchema;
  ui_schema: Record<string, unknown>;
  created_by: string;
  updated_by: string;
  created_at: string | null;
  updated_at: string | null;
}

export type AtomDefinitionSummary = Omit<AtomDefinitionRecord, 'input_schema' | 'output_schema' | 'ui_schema'>;

export interface AtomConfigTemplateRecord {
  id: number;
  name: string;
  atom_key: string;
  parameters: Record<string, unknown>;
  organization_id: number;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

export interface JsonSchema {
  type?: string | string[];
  title?: string;
  description?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  enum?: Array<string | number | boolean>;
  default?: unknown;
  format?: string;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
  uniqueItems?: boolean;
  maxProperties?: number;
  pattern?: string;
  items?: JsonSchema;
  additionalProperties?: boolean | JsonSchema;
  sensitive?: boolean;
  secretCompatible?: boolean;
  jsonEditorAllowed?: boolean;
  'x-widget'?: FormFieldWidget;
  'x-rows'?: number;
  'x-placeholder'?: string;
  'x-code-language'?: 'sh' | 'powershell' | 'python' | 'text';
  'x-target-binding'?: TargetFieldBinding;
  'x-file-options'?: FileFieldOptions;
  'x-enum-labels'?: Record<string, string>;
  'x-enum-usernames'?: Record<string, string>;
  'x-enum-metadata'?: Record<string, { scope?: 'personal' | 'team'; default_model?: string }>;
  'x-binding'?: 'literal-only';
}

export type NodeInputBinding =
  | { kind: 'literal'; value: unknown }
  | { kind: 'reference'; expression: string }
  | { kind: 'template'; template: string };

export interface TaskRecord {
  task_id: string;
  reference: string;
  type: string;
  system_type: string;
  status: string;
  worker_id: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  retry_count: number;
  iteration: number;
  retried_task_id: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  reason: string;
}

export interface AtomExecutionRecord {
  id: number;
  task_reference: string;
  atom_key: string;
  status: string;
  attempt: number;
  job_task_id: number | null;
  error_type: string;
  error_message: string;
}

export interface ExecutionArtifactRecord {
  id: string;
  format: 'docx' | 'xlsx';
  filename: string;
  size: number;
  summary: Record<string, number | string>;
  expires_at: string;
  download_url: string;
}

export type ExecutionNodeState = 'ACTIONABLE' | 'FAILED' | 'TIMED_OUT' | 'RUNNING' | 'WAITING' | 'WARNING' | 'SUCCESS' | 'SKIPPED' | 'UNREACHABLE' | 'PENDING';

export interface ExecutionNodeSummary {
  reference: string;
  name: string;
  task_type: 'START' | 'END' | ConductorTask['type'];
  task_name: string;
  parent_reference: string | null;
  branch_label: string | null;
  depth: number;
  state: ExecutionNodeState;
  state_counts: Partial<Record<ExecutionNodeState, number>>;
  instance_count: number;
  actionable_interaction_ids: string[];
  latest_finished_at: string | null;
}

export interface ExecutionNodesResponse {
  nodes: ExecutionNodeSummary[];
  default_node_reference: string;
}

export interface ExecutionNodeInstance {
  id: string;
  label: string;
  state?: ExecutionNodeState;
  attempt?: number;
  iteration?: number;
}

export interface ExecutionNodeInteraction {
  id: string;
  type: 'APPROVAL';
  status: WorkflowInteractionRecord['status'];
  title: string;
  description: string;
  public_context: Record<string, unknown>;
  candidate_users: string[];
  can_act: boolean;
  operator: string;
  decision: string;
  comment: string;
  created_at: string;
  due_at: string | null;
  handled_at: string | null;
}

export interface ExecutionNodeDetail {
  node: ExecutionNodeSummary;
  instances: ExecutionNodeInstance[];
  selected_instance_id: string | null;
  execution_info: Record<string, unknown>;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  system_context: Record<string, unknown>;
  error: { type?: string; message: string } | null;
  audit_events: Array<{ type: string; at: string | null; actor: string }>;
  artifacts: ExecutionArtifactRecord[];
  control: Record<string, unknown>;
  interaction: ExecutionNodeInteraction | null;
  technical: Record<string, unknown>;
}

export interface ExecutionRecord {
  id: string;
  workflow: number;
  workflow_name: string;
  workflow_enabled: boolean;
  workflow_deleted: boolean;
  workflow_version: number;
  conductor_workflow_id: string | null;
  status: ExecutionStatus;
  has_warnings: boolean;
  warning_count: number;
  trigger_type: WorkflowTriggerType;
  trigger_id?: string;
  mode: 'PRODUCTION' | 'DEBUG';
  debug_kind?: 'FULL' | 'NODE' | '';
  debug_task_reference?: string;
  parent_execution?: string | null;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  tasks: TaskRecord[];
  definition_snapshot: ConductorDefinition;
  resource_snapshot: Record<string, unknown>;
  target_snapshot: WorkflowTargetSnapshot;
  atom_executions: AtomExecutionRecord[];
  artifacts: ExecutionArtifactRecord[];
  artifact_count?: number;
  pending_approval_count?: number;
  actionable_approval_ids?: string[];
  waiting_node_summary?: string;
  error_message: string;
  failed_stage?: string;
  termination_reason?: string;
  started_by: string;
  created_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  updated_at: string;
  permission?: string[];
}

export interface WorkflowInteractionRecord {
  id: string;
  execution: string;
  workflow_name: string;
  workflow_version: number;
  execution_started_by: string;
  interaction_type: 'APPROVAL';
  task_reference: string;
  title: string;
  description: string;
  candidate_users: string[];
  public_context: Record<string, unknown>;
  output: Record<string, unknown>;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'TIMED_OUT' | 'CANCELLED';
  operator: string;
  decision: string;
  comment: string;
  due_at: string | null;
  handled_at: string | null;
  created_at: string;
}

export interface WorkflowTriggerRecord {
  id: string;
  workflow: number;
  workflow_name: string;
  node_key: string;
  name: string;
  trigger_type: WorkflowTriggerType;
  enabled: boolean;
  input_schema: JsonSchema;
  default_inputs: Record<string, unknown>;
  config: Record<string, unknown>;
  idempotency_window_seconds: number;
  next_run_at: string | null;
  last_run_at: string | null;
}

export interface AiModelRecord { id: number; name: string; model: string }
export interface AiProposalRecord {
  id: string;
  prompt: string;
  llm_model_id: number;
  llm_model_name: string;
  candidate_definition: ConductorDefinition;
  diff_summary: Record<string, unknown>;
  status: 'PENDING' | 'APPLIED' | 'REJECTED';
  created_at: string;
}

export interface WorkflowVersionRecord {
  id: number;
  version: number;
  definition: ConductorDefinition;
  canvas_metadata: Record<string, unknown>;
  resource_snapshot: Record<string, unknown>;
  change_summary: Record<string, unknown>;
  created_by: string;
  created_at: string;
  execution_count: number;
}
