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
  created_by?: string;
  created_at?: string;
  updated_at?: string;
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

export interface BuildRecord {
  id: number;
  knowledge_base: number;
  trigger: string;
  operator?: string;
  inputs?: Record<string, unknown>;
  stage: string;
  progress: number;
  counts?: Record<string, number>;
  affected_pages?: number[];
  errors?: string[];
  status: string;
  created_at?: string;
  updated_at?: string;
}

export interface CheckPage {
  id: number;
  title: string;
  page_type: string;
  body: string;
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
  suggested_actions?: string[];
  created_at?: string;
  updated_at?: string;
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

export interface WikiSearchHit {
  kind: string;
  id: number;
  title: string;
  snippet: string;
  score: number;
}

export interface WikiCitation {
  kind: string;
  id: number;
  title: string;
}

export interface WikiQaResult {
  answer: string;
  citations: WikiCitation[];
  contexts: WikiSearchHit[];
}

export interface GraphNode {
  id: number;
  title: string;
  page_type: string;
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

export interface WikiGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  clusters?: number[][];
  communities?: number[][];
  insights: Record<string, unknown>;
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
