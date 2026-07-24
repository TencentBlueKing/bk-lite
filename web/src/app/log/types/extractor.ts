export type ExtractorType =
  | 'copy'
  | 'split'
  | 'kv'
  | 'regex'
  | 'regex_replace'
  | 'json';

export type PublicationState = 'pending' | 'generating' | 'published' | 'failed';

export interface ExtractorConditionItem {
  field: string;
  op:
    | '=='
    | '!='
    | 'contains'
    | '!contains'
    | 'startswith'
    | 'endswith'
    | 'exists'
    | '!exists';
  value?: string | number | boolean | null;
}

export interface ExtractorCondition {
  mode: 'AND' | 'OR';
  conditions: ExtractorConditionItem[];
}

export interface LogExtractorRule {
  id: number;
  name: string;
  collect_instance: string;
  condition: ExtractorCondition;
  extractor_type: ExtractorType;
  source_field: string;
  target_field: string | null;
  delete_source: boolean;
  config: Record<string, unknown>;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface LogExtractorDraft {
  name: string;
  collect_instance: string;
  condition: ExtractorCondition;
  extractor_type: ExtractorType;
  source_field: string;
  target_field?: string | null;
  delete_source: boolean;
  config: Record<string, unknown>;
}

export interface ExtractorPublicationStatus {
  desired_generation: number;
  published_generation: number;
  status: PublicationState;
  last_error: string;
  last_published_at: string | null;
}

export interface LogExtractorListResponse {
  items: LogExtractorRule[];
  publication: ExtractorPublicationStatus;
}

export interface LogExtractorPreviewResult {
  event: Record<string, unknown>;
  results: Array<{
    status: 'success' | 'not_matched' | 'skipped' | 'failed';
    error: string | null;
  }>;
}
