export interface OpenApiCallLogRow {
  id?: number;
  created_at?: string;
  source_ip?: string;
  username?: string;
  team_name?: string | null;
  method?: string;
  path?: string;
  http_status?: number;
  error_code?: string;
  credential_type?: string;
  token_name?: string;
  token_id?: number | null;
  system_id?: string;
}

export interface OpenApiCallLogList {
  items?: OpenApiCallLogRow[];
  count?: number;
}

export function formatOpenApiCallRequest(row: OpenApiCallLogRow): string {
  const method = row.method || '--';
  const path = row.path || '--';
  return `${method} ${path}`;
}

export function openApiCallSucceeded(row: OpenApiCallLogRow): boolean {
  return (row.http_status ?? 500) < 400;
}

export function formatOpenApiCallResult(
  row: OpenApiCallLogRow,
  labels: { success: string; failure: string }
): string {
  return openApiCallSucceeded(row) ? labels.success : labels.failure;
}

export function openApiCallErrorCode(row: OpenApiCallLogRow): string {
  if (openApiCallSucceeded(row)) return '';
  return row.error_code || '';
}

export function formatOpenApiCallTokenKind(
  row: OpenApiCallLogRow,
  labels: { apiToken: string; systemToken: string }
): string {
  if (row.credential_type === 'api_token') return labels.apiToken;
  if (row.credential_type === 'system_token') return labels.systemToken;
  return '--';
}

export function formatOpenApiCallTokenSystemId(row: OpenApiCallLogRow): string {
  if (row.credential_type !== 'system_token') return '';
  return row.system_id || '';
}
