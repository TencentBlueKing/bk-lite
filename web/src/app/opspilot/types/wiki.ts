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

export type MaterialType = 'file' | 'web' | 'text';

export interface Material {
  id: number;
  knowledge_base: number;
  name: string;
  material_type: MaterialType;
  url?: string;
  text_content?: string;
  sync_policy?: { enabled?: boolean; interval_hours?: number };
  ocr_enhance?: boolean;
  content_hash?: string;
  ai_summary?: string;
  status?: string;
  error_message?: string;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface MaterialInfo {
  material: Material;
  original: string;
  file_url: string;
  ai_summary?: string;
  versions: Array<{ id: number; content_hash?: string; content_locator?: string; created_at?: string }>;
  contributed_pages: Array<{ id: number; title: string; page_type: string; status: string }>;
}

export interface MaterialBatchCreateResult {
  items: Material[];
  errors: Array<{ name: string; error: string }>;
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

export interface KnowledgePage {
  id: number;
  knowledge_base: number;
  page_type: string;
  title: string;
  tags: string[];
  contribution: string;
  update_method?: string;
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
  errors?: string[];
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

export type DecisionListView = 'pending' | 'processed';

export type WikiDecisionType = 'knowledge_conflict' | 'page_identity';

export type WikiDecisionRuleStatus = 'active' | 'revoked' | 'superseded';

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

// phase 7: 决策动作枚举(决策中心 API 接受)
export type CheckDecisionAction =
  // 知识冲突
  | 'keep_current'
  | 'use_new'
  | 'edit_accept'
  // 页面合并
  | 'keep_separate'
  | 'merge';

// 知识冲突决策三选一
export const KNOWLEDGE_CONFLICT_ACTIONS: CheckDecisionAction[] = [
  'keep_current',
  'use_new',
  'edit_accept',
];

// 页面合并决策二选一
export const PAGE_IDENTITY_ACTIONS: CheckDecisionAction[] = ['keep_separate', 'merge'];

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
  schema_md?: string;
}

export interface PurposeSchemaResult {
  purpose_md: string;
  schema_md: string;
  template_key?: string;
}

export interface WikiSearchExplanation {
  matched_by: Array<'keyword' | 'vector' | 'chunk_vector' | string>;
  keyword_score?: number;
  vector_score?: number;
  matched_terms?: string[];
  keyword_rank?: number;
  semantic_rank?: number;
  chunk_index?: number;
  fusion?: string;
}

export type WikiRetrievalMode = 'keyword' | 'hybrid' | 'chunk';

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
  rule: 'duplicate_canonical' | 'alias_only';
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
