export interface OpenApiCallLogRow {
  id?: number;
  created_at?: string;
  source_ip?: string;
  username?: string;
  team_id?: number | null;
  team_name?: string | null;
  method?: string;
  path?: string;
  http_status?: number;
  error_code?: string;
  credential_type?: string;
  token_name?: string;
  token_id?: number | null;
  system_id?: string;
  api_kind?: string;
  call_result?: 'success' | 'auth_passed' | 'auth_denied' | 'failure';
}

export interface OpenApiCallLogList {
  items?: OpenApiCallLogRow[];
  count?: number;
}

export interface OpenApiCallResultLabels {
  success: string;
  authPassed: string;
  authDenied: string;
  failure: string;
}

export function formatOpenApiCallRequest(row: OpenApiCallLogRow): string {
  const method = row.method || '--';
  const path = row.path || '--';
  return `${method} ${path}`;
}

export function formatOpenApiCallResult(
  row: OpenApiCallLogRow,
  labels: OpenApiCallResultLabels
): string {
  switch (row.call_result) {
    case 'success':
      return labels.success;
    case 'auth_passed':
      return labels.authPassed;
    case 'auth_denied':
      return labels.authDenied;
    case 'failure':
      return labels.failure;
    default:
      return labels.failure;
  }
}

export function openApiCallResultPositive(row: OpenApiCallLogRow): boolean {
  return row.call_result === 'success' || row.call_result === 'auth_passed';
}

export function openApiCallErrorCode(row: OpenApiCallLogRow): string {
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
