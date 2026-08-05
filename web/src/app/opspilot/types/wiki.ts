// Wiki 知识库相关类型(对齐后端 wiki_mgmt 序列化器)

export interface WikiKnowledgeBase {
  id: number;
  name: string;
  introduction?: string;
  team: (number | string)[];
  team_name?: string[];
  permissions?: string[];
  is_pinned?: boolean;
  purpose_md?: string;
  /** 兼容旧数据与模板提交；目录机器结构由结构化 revision 管理。 */
  schema_md?: string;
  llm_model?: number | null;
  embed_provider?: number | null;
  vision_model?: number | null;
  generation_language?: string;
  generation_rules?: Record<string, unknown>;
  web_sync_policy?: Record<string, unknown>;
  risk_rules?: Record<string, unknown>;
  template_key?: string;
  status?: string;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

export type MaterialType = "file" | "web" | "text";

export interface Material {
  id: number;
  knowledge_base: number;
  name: string;
  material_type: MaterialType;
  url?: string;
  text_content?: string;
  sync_policy?: { enabled?: boolean; interval_hours?: number };
  ocr_enhance?: boolean;
  source_relative_path?: string;
  source_identity?: string;
  source_folder_path?: string;
  content_hash?: string;
  ai_summary?: string;
  status?: string;
  error_message?: string;
  build_started_at?: string | null;
  build_finished_at?: string | null;
  build_duration_seconds?: number | null;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface MaterialInfo {
  material: Material;
  /** 文本资料原文，或网页 URL；文件资料通常为空串 */
  original: string;
  /** MarkItDown 转换后的完整 markdown（含图片增强描述） */
  parsed_markdown?: string;
  file_url: string;
  ai_summary?: string;
  versions: Array<{
    id: number;
    content_hash?: string;
    content_locator?: string;
    created_at?: string;
  }>;
  contributed_pages: Array<{
    id: number;
    title: string;
    page_type: string;
    status: string;
  }>;
}

export interface MaterialBatchCreateResult {
  items: Material[];
  errors: Array<{ name: string; error: string }>;
}

export interface MaterialFileUploadMetadata {
  source_relative_path?: string;
  classification_root_id?: number | null;
}

export interface MaterialBatchUploadEntry {
  file: File;
  source_relative_path?: string;
}

export interface MaterialDeleteImpact {
  material_id: number;
  material_name: string;
  affected_count: number;
  will_be_source_invalid_count: number;
  shared_source_protected_count: number;
  affected_pages: BuildAffectedPage[];
  will_be_source_invalid: BuildAffectedPage[];
  shared_source_protected: BuildAffectedPage[];
}

export interface MaterialImpactVersion {
  id: number;
  content_hash?: string;
  content_locator?: string;
  created_at?: string | null;
}

export interface MaterialUpdateImpact {
  material_id: number;
  material_name: string;
  material_status?: string;
  content_hash?: string;
  content_changed: boolean;
  latest_version?: MaterialImpactVersion | null;
  previous_version?: MaterialImpactVersion | null;
  affected_count: number;
  pending_review_count: number;
  affected_pages: BuildAffectedPage[];
  pending_review_pages: BuildAffectedPage[];
}

export interface WikiDirectoryBreadcrumbItem {
  id: number;
  key: string;
  name: string;
}

export interface WikiDirectoryNode {
  id: number;
  key: string;
  name: string;
  description?: string;
  parent_id?: number | null;
  order: number;
  status: string;
  is_system: boolean;
  accepts_pages: boolean;
  direct_page_count: number;
  total_page_count: number;
  children: WikiDirectoryNode[];
}

export type WikiDirectoryOrigin = "system" | "schema" | "manual";
export type WikiDirectoryLifecycleStatus =
  | "active"
  | "retired"
  | "merged"
  | "archived";

export interface WikiDirectoryTombstone {
  id: number;
  key: string;
  name: string;
  status: Exclude<WikiDirectoryLifecycleStatus, "active">;
  merged_into_id?: number | null;
}

export interface WikiDirectoryReadinessIssue {
  blocking: boolean;
  code: string;
  details: Record<string, unknown>;
  entity_id: number | string | null;
  entity_type: string | null;
  message: string;
  severity: "error" | "warning";
}

export interface WikiDirectoryReadinessResult {
  directory_enabled: boolean;
  issues: WikiDirectoryReadinessIssue[];
  knowledge_base_id: number;
  knowledge_base_name: string;
  mode: string;
  ready: boolean;
  scanned: Record<string, number>;
  summary: {
    blocking_issue_count: number;
    issue_count: number;
    warning_count: number;
  };
}

export interface WikiDirectoryEnableResult {
  knowledge_base_id: number;
  directory_enabled: true;
  changed: boolean;
  readiness: WikiDirectoryReadinessResult;
}

export interface WikiDirectoryTreeResult {
  enabled: boolean;
  unclassified_directory_id: number | null;
  structure_revision_id: number | null;
  structure_version: number | null;
  active_generation_id: number | null;
  directories: WikiDirectoryNode[];
  tombstones?: WikiDirectoryTombstone[];
}

export interface WikiPageDirectoryMutationResult {
  generation_id: number;
  previous_generation_id: number | null;
  active_generation_id: number;
  structure_revision_id: number;
  structure_version: number;
  changed: number;
  pages: Array<{
    id: number;
    directory_id: number;
    directory_key: string;
    directory_assignment_mode: "auto" | "manual";
    source: string;
  }>;
}

export interface WikiPageLifecycleStatusItem {
  id: number;
  status: "active" | "archived";
}

export interface WikiGenerationPageArchiveResult {
  generation_id: number;
  previous_generation_id: number | null;
  active_generation_id: number;
  structure_revision_id: number;
  structure_version: number;
  changed: number;
  pages: WikiPageLifecycleStatusItem[];
  build_record_id: number;
}

export type WikiPageDeleteResult = WikiGenerationPageArchiveResult;

export interface WikiGenerationPageBatchDeleteResult extends WikiGenerationPageArchiveResult {
  deleted: number;
}

export type WikiPageBatchDeleteResult = WikiGenerationPageBatchDeleteResult;

export interface WikiGenerationPageRestoreResult extends WikiPageDirectoryMutationResult {
  build_record_id: number;
}

export type WikiPageRestoreMutationResult = WikiGenerationPageRestoreResult;

export interface WikiPageRestoreFromArchiveResult {
  page: KnowledgePage;
  generation: WikiPageRestoreMutationResult;
}

export interface WikiStructureDirectoryRules {
  allowed_page_types: string[];
  default_for_page_types: string[];
}

export interface WikiExistingDirectoryRef {
  readonly id: number;
  readonly key: string;
}

export interface WikiNewDirectoryRef {
  readonly client_ref: string;
}

export type WikiStructureParentRef =
  | WikiExistingDirectoryRef
  | WikiNewDirectoryRef
  | null;

interface WikiStructureDirectoryFields {
  name: string;
  description: string;
  order: number;
  rules: WikiStructureDirectoryRules;
  parent: WikiStructureParentRef;
}

export interface WikiExistingStructureDirectory extends WikiStructureDirectoryFields {
  kind: "existing";
  readonly id: number;
  readonly key: string;
  readonly origin: WikiDirectoryOrigin;
  readonly status: WikiDirectoryLifecycleStatus;
}

export interface WikiNewStructureDirectory extends WikiStructureDirectoryFields {
  kind: "new";
  readonly client_ref: string;
}

export type WikiStructureSaveDirectory =
  | WikiExistingStructureDirectory
  | WikiNewStructureDirectory;

export interface WikiStructureSaveSnapshot {
  format_version: 1;
  page_types: string[];
  directories: WikiStructureSaveDirectory[];
}

export interface WikiFrozenStructureDirectory extends WikiStructureDirectoryFields {
  readonly id: number;
  readonly key: string;
  readonly origin: WikiDirectoryOrigin;
  readonly status: WikiDirectoryLifecycleStatus;
  parent: WikiExistingDirectoryRef | null;
}

export interface WikiFrozenStructureSnapshot {
  format_version: 1;
  page_types: string[];
  directories: WikiFrozenStructureDirectory[];
}

export interface WikiStructureRevisionSnapshot {
  readonly id: number;
  readonly version: number;
  readonly fingerprint: string;
}

export interface WikiActiveGenerationSnapshot {
  readonly id: number;
  readonly structure_revision_id: number;
  readonly structure_version: number;
  readonly status: "active";
}

export interface WikiStructureReadResult {
  structure_revision: WikiStructureRevisionSnapshot | null;
  active_generation: WikiActiveGenerationSnapshot | null;
  structure: WikiFrozenStructureSnapshot;
}

export interface WikiStructureSaveRequest {
  readonly structure_version: number;
  readonly base_generation_id: number;
  structure: WikiStructureSaveSnapshot;
}

export interface WikiStructureClientRefMapping {
  readonly client_ref: string;
  readonly id: number;
  readonly key: string;
}

export interface WikiStructureSaveResponse {
  structure_revision: WikiStructureRevisionSnapshot;
  active_generation: WikiActiveGenerationSnapshot;
  structure: WikiFrozenStructureSnapshot;
  client_ref_map: WikiStructureClientRefMapping[];
}

export type WikiDirectoryOperationAction = "merge" | "retire" | "archive";

export interface WikiDirectoryOperationRequest {
  structure_version: number;
  base_generation_id: number;
  action: WikiDirectoryOperationAction;
  source: WikiExistingDirectoryRef;
  target?: WikiExistingDirectoryRef;
}

export interface WikiDirectoryOperationConflict {
  code: string;
  details: string;
  source: WikiExistingDirectoryRef;
  target: WikiExistingDirectoryRef | null;
}

export interface WikiDirectoryOperationImpact {
  direct_page_count: number;
  descendant_page_count: number;
  manual_page_count: number;
  child_directory_count: number;
  conflicts: WikiDirectoryOperationConflict[];
  block_reasons: Array<{ code: string; details: string }>;
  redirect: {
    source: WikiExistingDirectoryRef;
    target: WikiExistingDirectoryRef;
  } | null;
}

export interface WikiDirectoryOperationPreview {
  impact: WikiDirectoryOperationImpact;
  can_execute: boolean;
  impact_hash: string;
  operation_token: string;
  expires_at: string;
  single_use: true;
  binding: WikiDirectoryOperationRequest & {
    knowledge_base_id: number;
    impact_hash: string;
  };
}

export interface WikiDirectoryOperationExecuteRequest extends WikiDirectoryOperationRequest {
  operation_token: string;
  impact_hash: string;
}

export interface WikiDirectoryOperationExecuteResult {
  structure_revision: WikiStructureRevisionSnapshot;
  active_generation: WikiActiveGenerationSnapshot;
  action_result: {
    action: WikiDirectoryOperationAction;
    source: WikiExistingDirectoryRef;
    target?: WikiExistingDirectoryRef;
    source_status: "merged" | "retired" | "archived";
    redirect: {
      source: WikiExistingDirectoryRef;
      target: WikiExistingDirectoryRef;
    } | null;
  };
}

export interface WikiGenerationRollbackRequest {
  readonly target_generation_id: number;
  readonly base_generation_id: number;
  readonly structure_version: number;
}

export interface WikiGenerationRollbackPreview {
  outcome: "compatible" | "requires_structure_restore" | "blocked";
  target_generation_id: number;
  structure_diff: Array<{
    code: string;
    path: string;
    details: string;
  }>;
  impact: {
    page_count: number;
    directory_count: number;
    relation_count: number;
  };
  allow_restore: boolean;
  block_reasons: Array<{
    code: string;
    details: string;
  }>;
}

export interface WikiGenerationRollbackExecuteRequest extends WikiGenerationRollbackRequest {
  readonly confirm_structure_restore: boolean;
}

export interface WikiGenerationRollbackExecuteResult {
  previous_generation: {
    id: number;
    status: "superseded";
  };
  active_generation: {
    id: number;
    kind: "rollback";
    rollback_of: number;
    structure_revision_id: number;
    structure_version: number;
    status: "active";
  };
  structure_result: {
    restored: boolean;
    previous_structure_revision_id: number;
    active_structure_revision_id: number;
    structure_version: number;
    fingerprint: string;
  };
}

export interface KnowledgePage {
  id: number;
  knowledge_base: number;
  generation_id?: number | null;
  directory?: number | null;
  directory_key?: string;
  directory_breadcrumb?: WikiDirectoryBreadcrumbItem[];
  directory_assignment_mode?: "auto" | "manual";
  page_type: string;
  title: string;
  tags: string[];
  contribution: string;
  update_method?: string;
  source_summary?: string;
  pending_conflict_count?: number;
  conflict_summary?: string;
  status: string;
  current_version?: number | null;
  body?: string;
  index_status?: string;
  chunk_index_status?: string;
  index_detail?: WikiIndexDetail;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface WikiIndexStageDetail {
  status: string;
  reason?: string;
  error?: string;
  build_record_id?: number;
  trigger?: string;
  stage?: string;
  indexed_chunks?: number;
  expected_chunks?: number;
}

export interface WikiIndexDetail {
  status?: string;
  page_embedding?: WikiIndexStageDetail;
  chunk_embedding?: WikiIndexStageDetail;
}

export interface PageVersion {
  id: number;
  page: number;
  no: number;
  body: string;
  change_type: string;
  is_current: boolean;
  created_by?: string;
  created_at?: string;
}

export interface WikiPageSource {
  id: number;
  material: {
    id: number;
    name: string;
    material_type: MaterialType;
    status?: string;
  };
  material_version?: {
    id: number;
    content_hash?: string;
    content_locator?: string;
    created_at?: string;
  } | null;
  locator: BuildSourceLocator;
  locator_raw?: string;
  snippet?: string;
}

export interface WikiPageSourcesResult {
  page_id: number;
  page_title: string;
  sources: WikiPageSource[];
}

export interface BuildAffectedPage {
  id: number;
  title: string;
  page_type: string;
  status: string;
  reason?: string;
}

export interface BuildMaintenanceStage {
  status?: string;
  count?: number;
  error?: string;
  reason?: string;
}

export interface BuildMaintenance {
  status?: string;
  event?: string;
  affected_page_ids?: number[];
  stages?: Record<string, BuildMaintenanceStage>;
  [key: string]: unknown;
}

export interface BuildSourceChunk {
  index: number;
  start: number;
  end: number;
  preview: string;
}

export interface BuildSourceLocator {
  kind?: string;
  chunk_index?: number;
  chunk_count?: number;
  start?: number;
  end?: number;
  snippet?: string;
  [key: string]: unknown;
}

export interface BuildPageAction {
  page_id: number;
  title: string;
  page_type: string;
  status: string;
  action: string;
  source_locator?: BuildSourceLocator;
}

export interface BuildSourceMaterialTrace {
  material_id: number;
  material_name: string;
  chunks?: BuildSourceChunk[];
  page_actions?: BuildPageAction[];
}

export interface BuildSourceTrace {
  chunks?: BuildSourceChunk[];
  page_actions?: BuildPageAction[];
  materials?: BuildSourceMaterialTrace[];
}

export interface BuildRecord {
  id: number;
  knowledge_base: number;
  trigger: string;
  operator?: string;
  inputs?: Record<string, unknown> & {
    material_name?: string;
    source_trace?: BuildSourceTrace;
  };
  input_label?: string;
  stage: string;
  progress: number;
  counts?: Record<string, number>;
  affected_pages?: number[];
  affected_page_details?: BuildAffectedPage[];
  errors?: unknown[];
  budget_trace?: Record<string, unknown>;
  checkpoint?: Record<string, unknown>;
  maintenance?: BuildMaintenance;
  status: string;
  created_at?: string;
  updated_at?: string;
}

export interface BuildMaintenanceBatchRetryResult {
  retried: number;
  skipped: number;
  skipped_ids: number[];
  items: BuildRecord[];
}

export interface MarkdownImportResult {
  created: number;
  updated: number;
  skipped: number;
  pages: BuildAffectedPage[];
  build_record?: BuildRecord;
}

export type WikiMarkdownImportArchiveKind =
  | "markdown"
  | "native"
  | "opspilot_native"
  | "third_party";

export type WikiMarkdownImportAction = "create" | "update" | "candidate";

export interface WikiMarkdownImportDirectoryTrace {
  directory_id: number | null;
  directory_key: string;
  pending_client_ref?: string;
  assignment_mode: "auto" | "manual";
  source: string;
  trace: string[];
  route_reason: string;
  suggestion: {
    key?: string | null;
    source?: string;
    reason?: string;
    confidence?: number | null;
    schema_mismatch?: boolean;
    low_confidence?: boolean;
  };
  redirect_chain: string[];
  structure_revision: {
    id: number | null;
    revision_no: number | null;
    fingerprint: string;
  };
}

export interface WikiMarkdownImportFolderPreview {
  folder_path: string;
  client_ref: string;
  name: string;
}

export interface WikiMarkdownImportStructurePreview {
  restore_native_structure?: boolean;
  create_directories_from_folders?: boolean;
  create_directory_count?: number;
  directories?: WikiMarkdownImportFolderPreview[];
}

export interface WikiMarkdownImportPreviewPage {
  archive_path: string;
  title: string;
  page_type: string;
  content_sha256: string;
  existing_page_id: number | null;
  action: WikiMarkdownImportAction;
  directory?: WikiMarkdownImportDirectoryTrace;
}

export interface WikiMarkdownImportPreview {
  archive_kind: WikiMarkdownImportArchiveKind;
  archive_sha256: string;
  skipped_entries: number;
  pages: WikiMarkdownImportPreviewPage[];
  counts: {
    total: number;
    create: number;
    update: number;
    candidate: number;
  };
  native_structure_available: boolean;
  restore_structure_requested: boolean;
  create_directories_from_folders_requested?: boolean;
  structure_preview?: WikiMarkdownImportStructurePreview | null;
}

export interface WikiMarkdownImportPreflightOptions {
  classification_root_id?: number | null;
  target_directory_id?: number | null;
  path_mappings?: Record<string, number | string>;
  restore_structure?: boolean;
  restore_native_structure?: boolean;
  create_directories_from_folders?: boolean;
}

export interface WikiMarkdownImportPreflightResult {
  token: string;
  expires_in_seconds: number;
  preview: WikiMarkdownImportPreview;
  base_generation_id: number | null;
  structure_revision_id: number | null;
  structure_version: number | null;
}

export interface WikiMarkdownImportExecutePage {
  page_id: number;
  title: string;
  action: WikiMarkdownImportAction;
  archive_path: string;
  directory_id?: number | null;
  check_id?: number;
}

export interface WikiMarkdownImportExecuteResult {
  build_record_id?: number;
  generation_id?: number;
  counts?: {
    created?: number;
    updated?: number;
    candidate?: number;
  };
  pages?: WikiMarkdownImportExecutePage[];
  relations?: Record<string, unknown>;
  structure_restore?: Record<string, unknown>;
  folder_structure?: {
    created_directory_count: number;
    directories: Array<{
      folder_path: string;
      directory_id: number;
      directory_key: string;
      created: boolean;
    }>;
    structure_revision?: WikiStructureRevisionSnapshot | null;
    governance_generation?: WikiActiveGenerationSnapshot | null;
  };
  created?: number;
  updated?: number;
  skipped?: number;
}

export type WikiDecisionType = "knowledge_conflict" | "page_identity";

export type WikiDecisionRuleStatus = "active" | "revoked" | "superseded";

export interface WikiDecisionRule {
  id: number;
  status: WikiDecisionRuleStatus;
  action: CheckDecisionAction;
  match_snapshot: Record<string, unknown>;
  result_snapshot: Record<string, unknown>;
  replay_count: number;
  last_replayed_at?: string | null;
  revoked_reason?: string;
  created_at?: string;
  updated_at?: string;
}

export interface CheckPage {
  id: number;
  page_id?: number;
  title: string;
  page_type: string;
  body: string;
  contribution?: string;
  current_version?: number | null;
  version_id?: number | null;
  source_count?: number;
  relation_count?: number;
  source_label?: string;
  version_label?: string;
  material_id?: number;
  material_version_id?: number;
  content_hash?: string;
}

export interface CheckItem {
  id: number;
  knowledge_base: number;
  check_type: string;
  status: string;
  related?: Record<string, unknown>;
  related_pages?: CheckPage[];
  candidate_version?: number | null;
  candidate?: { id: number; body: string } | null;
  current_knowledge?: CheckPage | null;
  new_knowledge?: CheckPage | null;
  suggested_actions?: string[];
  assignee?: string;
  due_at?: string | null;
  action_type?: string;
  created_at?: string;
  updated_at?: string;
  // phase 7: 决策中心字段
  decision_key?: string;
  decision_context?: Record<string, unknown>;
  decision_type?: WikiDecisionType;
  decision_action?: CheckDecisionAction;
  decision_operator?: string;
  decision_processed_at?: string;
  decision_rule?: WikiDecisionRule | null;
}

export type DecisionListView = "pending" | "processed";

// phase 7: 决策动作枚举(决策中心 API 接受)
export type CheckDecisionAction =
  // 知识冲突
  | "keep_current"
  | "use_new"
  | "edit_accept"
  // 页面合并
  | "keep_separate"
  | "merge";

// 知识冲突决策三选一
export const KNOWLEDGE_CONFLICT_ACTIONS: CheckDecisionAction[] = [
  "keep_current",
  "use_new",
  "edit_accept",
];

// 页面合并决策二选一
export const PAGE_IDENTITY_ACTIONS: CheckDecisionAction[] = [
  "keep_separate",
  "merge",
];

export interface FetchDecisionItemsParams {
  view: DecisionListView;
  page?: number;
  page_size?: number;
}

export interface CheckDecisionRequest {
  action: CheckDecisionAction;
  body?: string;
  material_id?: number;
}

export interface CheckDecisionResponse {
  check: CheckItem;
  rule_id: number | null;
}

export interface RevokeDecisionRuleRequest {
  rule_id?: number;
  reason?: string;
}

export interface RevokeDecisionRuleResponse {
  check: CheckItem;
}

export interface FetchDecisionItemsParams {
  view: DecisionListView;
  page?: number;
  page_size?: number;
}

export interface CheckDecisionRequest {
  action: CheckDecisionAction;
  body?: string;
  material_id?: number;
}

export interface CheckDecisionResponse {
  check: CheckItem;
  rule_id: number | null;
}

export interface RevokeDecisionRuleRequest {
  rule_id?: number;
  reason?: string;
}

export interface RevokeDecisionRuleResponse {
  check: CheckItem;
}

export interface PurposeSchemaTemplate {
  key: string;
  name: string;
  description?: string;
  purpose_md?: string;
  /** 仅用于模板/后端兼容，不作为管理员可编辑的目录结构。 */
  schema_md?: string;
}

export interface PurposeSchemaResult {
  purpose_md: string;
  schema_md: string;
  template_key?: string;
}

export interface WikiSearchExplanation {
  matched_by: Array<"keyword" | "vector" | "chunk_vector" | string>;
  keyword_score?: number;
  vector_score?: number;
  matched_terms?: string[];
  keyword_rank?: number;
  semantic_rank?: number;
  chunk_index?: number;
  fusion?: string;
}

export type WikiRetrievalMode = "keyword" | "hybrid" | "chunk";

export interface WikiSearchHit {
  kind: string;
  id: number | string;
  title: string;
  snippet: string;
  score: number;
  explanation?: WikiSearchExplanation;
}

export interface WikiCitation {
  kind: string;
  id: number;
  title: string;
  explanation?: WikiSearchExplanation;
}

export interface WikiContextOptions {
  top_k?: number;
  token_budget?: number;
  graph_hops?: number;
  retrieval_mode?: WikiRetrievalMode;
}

export interface WikiContextBudget {
  token_budget?: number | null;
  used_tokens: number;
  truncated: boolean;
}

export interface WikiContextCitation extends WikiCitation {
  n: number;
  kb_id: number;
}

export interface WikiContextHit extends WikiSearchHit {
  kb_id?: number;
  kb_name?: string;
  page_id?: number;
  heading_path?: string;
}

export interface WikiContextResult {
  context: string;
  citations: WikiContextCitation[];
  hits: WikiContextHit[];
  budget: WikiContextBudget;
  retrieval_mode: WikiRetrievalMode | string;
}

export interface WikiQaResult {
  answer: string;
  citations: WikiCitation[];
  contexts: WikiSearchHit[];
  mode?: "llm" | "fallback" | "empty" | string;
  finish_reason?: string;
  output_truncated?: boolean;
  warning_code?: string;
  warning?: string;
}

export interface WikiQaStreamMeta {
  event: "meta";
  mode?: string;
  citations?: WikiCitation[];
  contexts?: WikiSearchHit[];
  warning_code?: string;
  warning?: string;
}

export interface WikiQaStreamDelta {
  event: "delta";
  text: string;
}

export interface WikiQaStreamDone {
  event: "done";
  answer: string;
  finish_reason?: string;
  output_truncated?: boolean;
  mode?: string;
  warning_code?: string;
  warning?: string;
}

export interface WikiQaStreamError {
  event: "error";
  message?: string;
  code?: string;
  fallback?: boolean;
  details?: unknown;
}

export type WikiQaStreamEvent =
  | WikiQaStreamMeta
  | WikiQaStreamDelta
  | WikiQaStreamDone
  | WikiQaStreamError;

export interface WikiQaStreamHandlers {
  onMeta?: (meta: WikiQaStreamMeta) => void;
  onDelta?: (text: string) => void;
  onDone?: (done: WikiQaStreamDone) => void;
  onError?: (error: WikiQaStreamError) => void;
}

export interface SaveAnswerPageInput {
  knowledge_base: number;
  title: string;
  page_type: string;
  body: string;
  tags?: string[];
  source_conversation_id: string;
  source_message_id?: string;
  source_channel?: string;
}

export type SaveAnswerPageResult = KnowledgePage;

export interface GraphNode {
  id: number;
  title: string;
  page_type: string;
  page_ids?: number[];
  aliases?: string[];
  cluster?: number;
  community?: number;
  degree?: number;
  directory_id?: number | null;
  directory_key?: string;
  directory_breadcrumb?: WikiDirectoryBreadcrumbItem[];
}

export interface GraphEdge {
  from: number;
  to: number;
  weight?: number;
  relation_type?: string;
  signals?: Record<string, number>;
}

export interface WikiGraphBridgeNode {
  id: number;
  title: string;
  degree: number;
  component_count_after_removal: number;
}

export interface WikiGraphSparseCommunity {
  page_ids: number[];
  titles: string[];
  size: number;
  edge_count: number;
  possible_edges: number;
  density: number;
}

export interface WikiGraphCrossCommunityEdge {
  from: number;
  to: number;
  from_title?: string;
  to_title?: string;
  weight: number;
  signals: Record<string, number>;
  from_community: number;
  to_community: number;
}

export interface WikiGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  clusters?: number[][];
  communities?: number[][];
  insights: Record<string, unknown>;
}

export interface WikiPreviewMergeGroup {
  canonical: string;
  merged_pages: string[];
  page_ids: number[];
  rule: "duplicate_canonical" | "alias_only";
}

export interface WikiPreviewMergeResult {
  merges: WikiPreviewMergeGroup[];
  total_canonical_groups: number;
  active_page_count: number;
}

export interface WikiOverview {
  knowledge_base: { id: number; name: string; status: string };
  counts: Record<string, number>;
  contribution: Record<string, number>;
  material_status: Record<string, number>;
  checks_by_type: Record<string, number>;
  health: Record<string, unknown>;
  recent_builds: Array<Record<string, unknown>>;
  recent_pages?: Array<Record<string, unknown>>;
  agents?: Array<{ id: number; name: string }>;
}
