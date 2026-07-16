export type OpsAnalysisObjectType =
  | 'dashboard'
  | 'topology'
  | 'architecture'
  | 'datasource'
  | 'namespace';

export type ConflictAction = 'skip' | 'overwrite' | 'rename';

export interface PrecheckRequest {
  yaml_content: string;
  target_directory_id?: number | null;
}

export interface ConflictItem {
  object_key: string;
  object_type: OpsAnalysisObjectType;
  reason: string;
  suggested_actions: ConflictAction[];
}

export interface WarningItem {
  code: string;
  message: string;
  object_key?: string;
  field?: string;
}

export interface ErrorItem {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ObjectCounts {
  total: number;
  by_type: Record<OpsAnalysisObjectType, number>;
}

export interface PrecheckResponse {
  valid: boolean;
  counts: ObjectCounts;
  conflicts: ConflictItem[];
  warnings: WarningItem[];
  errors: ErrorItem[];
}

export interface ConflictDecision {
  object_key: string;
  action: ConflictAction;
}

export interface SecretSupplement {
  object_key: string;
  field: string;
  value: string;
}

export interface ImportSubmitRequest {
  yaml_content: string;
  target_directory_id?: number | null;
  conflict_decisions?: ConflictDecision[];
  secret_supplements?: SecretSupplement[];
}

export interface ImportResultItem {
  object_key: string;
  object_type: OpsAnalysisObjectType;
  status: 'success' | 'failed' | 'skipped' | 'overwritten';
  message: string;
  new_id: number | null;
}

export interface ImportSummary {
  total: number;
  success: number;
  failed: number;
  skipped: number;
  overwritten: number;
}

export interface ImportSubmitResponse {
  success: boolean;
  results: ImportResultItem[];
  summary: ImportSummary;
}
