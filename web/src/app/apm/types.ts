export type CatalogStatus = 'active' | 'silent' | 'archived';

export interface ApmEnvironmentView {
  environment: string;
  last_seen_at: string;
  status: CatalogStatus;
}

export interface ApmService {
  id: string;
  namespace: string;
  name: string;
  first_seen_at: string;
  last_seen_at: string;
  archived_at: string | null;
  archive_reason: string;
  status: CatalogStatus;
  environment_views: ApmEnvironmentView[];
  organization_ids: number[];
}

export interface ApmServiceInstance {
  id: string;
  service_namespace: string;
  service_name: string;
  instance_id: string;
  environment: string;
  version: string;
  ingest_source_id: string;
  ingest_source_name: string;
  permission_mode: 'inherited' | 'custom';
  first_seen_at: string;
  last_seen_at: string;
  archived_at: string | null;
  archive_reason: string;
  status: CatalogStatus;
  organization_ids: number[];
}

export interface ApmServiceRed {
  service_id: string;
  environment: string;
  started_at: string;
  ended_at: string;
  request_rate: number;
  error_rate: number;
  p95_ms: number;
  p99_ms: number;
  timeseries: ApmServiceRedPoint[];
  top_endpoints: ApmServiceEndpointRed[];
}

export interface ApmServiceRedPoint {
  timestamp: string;
  request_rate: number;
  error_rate: number;
  p95_ms: number;
  p99_ms: number;
}

export interface ApmServiceEndpointRed {
  endpoint: string;
  request_rate: number;
  error_rate: number;
  p95_ms: number;
  p99_ms: number;
}

export interface ApmIngestSource {
  id: string;
  name: string;
  ingest_type: 'otlp_http' | 'otlp_grpc';
  cloud_region_id: number | null;
  environment_hint: string;
  credential_prefix: string;
  is_enabled: boolean;
  first_received_at: string | null;
  last_received_at: string | null;
  last_missing_instance_identity_at: string | null;
  missing_instance_identity: boolean;
  organization_ids: number[];
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

export interface ApmIngestSourceInput {
  name: string;
  ingest_type: ApmIngestSource['ingest_type'];
  organization_ids: number[];
  cloud_region_id?: number | null;
  environment_hint?: string;
}

export interface ApmIngestSourceWithCredential extends ApmIngestSource {
  credential: string;
}

export interface ApmIngestSnippetInput {
  credential: string;
  language: 'python' | 'nodejs' | 'java' | 'go';
  runtime: 'kubernetes' | 'docker' | 'host' | 'other';
  endpoint: string;
  service_namespace: string;
  service_name: string;
  environment: string;
}

export interface ApmIngestSnippet {
  environment: Record<string, string>;
  code: string;
}

export interface ApmHealth {
  catalog_reconcile: {
    status: 'pending' | 'ok' | 'degraded';
    last_succeeded_at?: string;
    last_failed_at?: string;
  };
}

export interface ApmTraceSummary {
  trace_id: string;
  started_at: string;
  duration_ms: number;
  service_namespace: string;
  service_name: string;
  environment: string;
  instance_id: string | null;
  status: 'ok' | 'error';
  root_span_name: string;
  span_count: number;
}

export interface ApmTracePage {
  items: ApmTraceSummary[];
  next_cursor: string | null;
}

export interface ApmSpanDetail {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  started_at: string;
  duration_ms: number;
  status: 'ok' | 'error';
  attributes: Record<string, unknown>;
  service_namespace: string;
  service_name: string;
  environment: string;
  instance_id: string | null;
  kind: string;
}

export interface ApmTraceDetail {
  trace_id: string;
  service_namespace: string;
  service_name: string;
  environment: string;
  instance_id: string | null;
  truncated: boolean;
  spans: ApmSpanDetail[];
}

export interface ApmTraceSearchParams {
  service_namespace?: string;
  service_name: string;
  environment: string;
  instance_id?: string;
  started_at?: string;
  ended_at?: string;
  cursor?: string;
  limit?: number;
}

export type ApmPolicyMetric = 'error_rate' | 'p95' | 'p99' | 'throughput' | 'no_traffic';
export type ApmPolicyComparator = 'gt' | 'gte' | 'lt' | 'lte';
export type ApmPolicySeverity = 'critical' | 'error' | 'warning';

export interface ApmPolicyInput {
  name: string;
  service_id: string;
  environment: string;
  metric_type: ApmPolicyMetric;
  comparator: ApmPolicyComparator;
  threshold: number | string;
  duration_window: number;
  recovery_window: number;
  severity: ApmPolicySeverity;
  notice: boolean;
  notice_type_ids: number[];
  notice_users: string[];
  is_enabled: boolean;
}

export interface ApmPolicy extends Omit<ApmPolicyInput, 'threshold'> {
  id: string;
  threshold: string;
  service_namespace: string;
  service_name: string;
  state: {
    status: 'normal' | 'firing';
    consecutive_hits: number;
    consecutive_recoveries: number;
    last_succeeded_at: string | null;
    last_failed_at: string | null;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface ApmPolicyQueryResult {
  value: string;
  breached: boolean;
  evaluated_at: string;
}

export interface ApmEvent {
  id: string;
  event_id: string;
  external_id: string;
  title: string;
  description: string;
  severity: ApmPolicySeverity | 'info';
  action: 'created' | 'recovery';
  status: string;
  service: string;
  item: ApmPolicyMetric;
  value: number | null;
  resource_id: string;
  resource_name: string;
  start_time: string;
  end_time: string | null;
  received_at: string;
  policy_id: string | null;
  environment: string;
}

export interface ApmEventQuery {
  action?: ApmEvent['action'];
  severity?: ApmPolicySeverity;
  started_at?: string;
  ended_at?: string;
  limit?: number;
}

export interface ApmNotificationChannel {
  id: number;
  name: string;
  channel_type: 'nats';
  description: string;
}
