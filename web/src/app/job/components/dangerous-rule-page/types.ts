export type DangerousRuleMatchType = 'exact' | 'regex';

export interface DangerousRule {
  id: number;
  name: string;
  description: string;
  pattern: string;
  match_type?: DangerousRuleMatchType;
  level: 'confirm' | 'forbidden';
  is_enabled: boolean;
  team: number[];
  created_by: string;
  created_at: string;
  updated_by: string;
  updated_at: string;
}

export interface DangerousRuleListResponse {
  count: number;
  items: DangerousRule[];
}

export interface DangerousRuleParams {
  page?: number;
  page_size?: number;
  search?: string;
  level?: 'confirm' | 'forbidden';
  match_type?: DangerousRuleMatchType;
  is_enabled?: boolean;
  name?: string;
  pattern?: string;
  team?: string;
}

export interface DangerousRuleFormData {
  name: string;
  description?: string;
  pattern: string;
  match_type?: DangerousRuleMatchType;
  level: 'confirm' | 'forbidden';
  is_enabled?: boolean;
  team?: number[];
}
