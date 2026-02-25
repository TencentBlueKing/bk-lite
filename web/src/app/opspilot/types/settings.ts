export interface QuotaData {
  label: string;
  usage: number;
  total: number;
  unit: string;
}

export interface QuotaRule {
  id: number;
  name: string;
  target_type: string;
  target_list: string[];
  rule_type: string;
  file_size: number;
  unit: string;
  skill_count: number;
  bot_count: number;
}

export interface QuotaRulePayload {
  name: string;
  target_type: string;
  target_list: string[];
  rule_type: string;
  file_size: number;
  unit: string;
  skill_count: number;
  bot_count: number;
}

export interface QuotaFormValues {
  id?: number;
  name: string;
  targetType?: string;
  target_type?: string;
  targetList?: string[];
  target_list?: string[];
  rule?: string;
  rule_type?: string;
  file_size?: string | number;
  unit?: string;
  skills?: string | number;
  skill_count?: number;
  bots?: string | number;
  bot_count?: number;
}

export interface QuotaModalProps {
  visible: boolean;
  onConfirm: (values: QuotaFormValues) => Promise<void>;
  onCancel: () => void;
  mode: 'add' | 'edit';
  initialValues?: QuotaFormValues | null;
}

export interface TargetOption {
  id: string;
  name: string;
}

export interface QuotaRuleParams {
  page?: number;
  page_size?: number;
  name?: string;
}

export interface QuotaRuleResponse {
  items: QuotaRule[];
  count: number;
}

export interface GroupUser {
  username: string;
  [key: string]: unknown;
}

export interface ModelOption {
  id: number;
  name: string;
  enabled: boolean;
}

export interface MyQuotaResponse {
  is_file_uniform: boolean;
  used_file_size: number;
  all_file_size: number;
  is_skill_uniform: boolean;
  used_skill_count: number;
  all_skill_count: number;
  is_bot_uniform: boolean;
  used_bot_count: number;
  all_bot_count: number;
}
