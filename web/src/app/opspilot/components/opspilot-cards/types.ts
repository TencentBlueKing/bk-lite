export interface OpsPilotStudioCardRecord {
  id: number;
  name: string;
  introduction: string;
  created_by: string;
  team: string[];
  team_name: string[];
  online: boolean;
  is_pinned?: boolean;
  bot_type?: number;
  permissions?: string[];
}

export interface OpsPilotSkillCardRecord {
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

export interface OpsPilotApprovalRequest {
  execution_id: string;
  node_id: string;
  tool_call_id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  timeout_seconds: number;
  received_at: number;
  status: 'pending' | 'approved' | 'rejected';
}
