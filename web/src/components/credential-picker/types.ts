export const CREDENTIAL_MENU_PATH = '/system-manager/credential';

export const CREDENTIAL_CATEGORIES = [
  'host',
  'network',
  'storage',
  'database',
  'middleware',
  'cloud',
  'other',
] as const;

export type CredentialCategoryId = (typeof CREDENTIAL_CATEGORIES)[number];

export const CREDENTIAL_CATEGORY_ZH_LABELS: Record<CredentialCategoryId, string> = {
  host: '主机',
  network: '网络',
  storage: '存储',
  database: '数据库',
  middleware: '中间件',
  cloud: '云平台',
  other: '其他',
};

export type CredentialFieldKind = 'string' | 'number' | 'secret' | 'enum';

export type CredentialVisibleWhenCondition =
  | string
  | { op: 'eq' | 'ne'; value: string };

export interface CredentialFieldSchema {
  id: string;
  name?: string;
  kind: CredentialFieldKind;
  required?: boolean;
  values?: string[];
  widget?: 'textarea';
  default?: string;
  visible_when?: Record<string, CredentialVisibleWhenCondition>;
}

export interface CredentialTypeItem {
  key: string;
  name: string;
  is_builtin: boolean;
  categories: string[];
  fields: CredentialFieldSchema[];
  credential_count?: number;
}

export interface CredentialItem {
  credential_id: string;
  name: string;
  type: string;
  group_id: number;
  disabled: boolean;
  fields: Record<string, unknown>;
  refs?: { module: string; count: number }[] | null;
}

export interface CredentialGroupOption {
  id: number;
  name: string;
}

export interface CredentialCreatePayload {
  name: string;
  type: string;
  group_id: number;
  fields: Record<string, unknown>;
}
