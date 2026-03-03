export interface Skill {
  id: number;
  name: string;
  introduction: string;
  created_by: string;
  team: string[];
  team_name: string;
  is_pinned?: boolean;
  permissions?: string[];
  skill_type?: number;
  is_template?: boolean;
  llm_model_name?: string;
}

export interface ModifySkillModalProps {
  visible: boolean;
  onCancel: () => void;
  onConfirm: (values: Skill) => void;
  initialValues?: Skill | null;
}

export interface RagScoreThresholdItem {
  knowledge_base: number;
  score: number;
}

export interface KnowledgeBase {
  id: number;
  name: string;
  introduction?: string;
}

export interface SelectorOption {
  id: number;
  name: string;
  icon?: string;
  description?: string;
}

export interface KnowledgeBaseRagSource {
  id: number,
  name: string,
  introduction: string,
  score?: number
}

export interface InvocationLogParams {
  skill_id?: string | number;
  start_time?: string;
  end_time?: string;
  page?: number;
  page_size?: number;
}

export interface InvocationLog {
  id: number;
  created_at: string;
  input_data: string;
  output_data: string;
  status: string;
  execution_duration?: number;
}

export interface InvocationLogResponse {
  items: InvocationLog[];
  count: number;
}

export interface SkillListParams {
  page?: number;
  page_size?: number;
  search?: string;
  is_template?: boolean | number;
}

export interface SkillListResponse {
  items: Skill[];
  count: number;
}

export interface SkillDetail extends Skill {
  llm_model?: number;
  knowledge_base?: number[];
  knowledge_base_ids?: number[];
  tool_ids?: number[];
  prompt_template?: string;
  rag_config?: RagConfig;
  temperature?: number;
  skill_prompt?: string;
  guide?: string;
  show_think?: boolean;
  enable_suggest?: boolean;
  enable_query_rewrite?: boolean;
  enable_conversation_history?: boolean;
  enable_rag?: boolean;
  enable_rag_strict_mode?: boolean;
  enable_rag_knowledge_source?: boolean;
  rag_score_threshold?: RagScoreThresholdItem[];
  conversation_window_size?: number;
  tools?: unknown[];
  enable_km_route?: boolean;
  km_llm_model?: number;
  desc?: string;
}

export interface RagConfig {
  enabled: boolean;
  top_k?: number;
  score_threshold?: number;
  rag_score_thresholds?: RagScoreThresholdItem[];
}

export interface Rule {
  id: number;
  key: string;
  name: string;
  description?: string;
  condition: RuleCondition | string;
  action: string;
  action_set?: RuleActionSet;
  skill_id?: number;
  priority?: number;
  enabled?: boolean;
  is_enabled?: boolean;
  created_at?: string;
  created_by?: string;
}

export interface RuleCondition {
  operator: string;
  conditions: RuleConditionItem[];
}

export interface RuleConditionItem {
  type: string;
  obj: string;
  value: string;
}

export interface RuleActionSet {
  skill_prompt?: string;
  knowledge_base_list?: number[];
}

export interface RuleParams {
  skill_id?: string | number;
  page?: number;
  page_size?: number;
  name?: string;
}

export interface RuleResponse {
  items: Rule[];
  count: number;
}

export interface RulePayload {
  skill?: string | number | null;
  name: string;
  description?: string;
  condition: RuleCondition | string;
  action: string;
  action_set?: RuleActionSet;
  skill_id?: number;
  priority?: number;
  enabled?: boolean;
  is_enabled?: boolean;
}

export interface LlmModel {
  id: number;
  name: string;
  enabled: boolean;
  provider?: string;
  llm_model_type?: string;
}

export interface SkillDetailPayload {
  name?: string;
  introduction?: string;
  team?: string[];
  llm_model?: number;
  knowledge_base_ids?: number[];
  tool_ids?: number[];
  prompt_template?: string;
  rag_config?: RagConfig;
  [key: string]: unknown;
}

export interface SkillTool {
  id: number;
  name: string;
  description?: string;
  icon?: string;
  enabled: boolean;
}

export interface SkillTemplate {
  id: number;
  name: string;
  introduction: string;
  skill_type: number;
}

export interface CreateSkillPayload {
  name: string;
  introduction: string;
  team: string[];
  skill_type: number;
}
