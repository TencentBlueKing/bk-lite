export type CatalogStatus = 'active' | 'silent' | 'archived';
export type InstanceStatus = 'active' | 'silent';

export interface ApmPage<T> {
  count: number;
  items: T[];
}

export interface ApmEnvironmentView {
  environment: string;
  last_seen_at: string;
  status: CatalogStatus;
}

export interface ApmService {
  id: string;
  application_id: string;
  application_name: string;
  namespace: string;
  name: string;
  language: string;
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
  application_id: string;
  application_name: string;
  permission_mode: 'inherited' | 'custom';
  first_seen_at: string;
  last_seen_at: string;
  status: InstanceStatus;
  organization_ids: number[];
}

export interface ApmServiceRed {
  service_id: string;
  environment: string;
  started_at: string;
  ended_at: string;
  request_rate: number | null;
  error_rate: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  timeseries: ApmServiceRedPoint[];
  top_endpoints: ApmServiceEndpointRed[];
}

export interface ApmServiceRedPoint {
  timestamp: string;
  request_rate: number | null;
  error_rate: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
}

export interface ApmServiceEndpointRed {
  endpoint: string;
  request_rate: number;
  error_rate: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
}

export type ApmSliType = 'availability' | 'latency_p95' | 'latency_p99';
export type ApmSloEvaluationWindow = 'rolling7d' | 'rolling30d' | 'calendarMonth';
export type ApmMetricDataState = 'available' | 'no_data' | 'unavailable';

export interface ApmSloInput {
  name: string;
  service_id: string;
  environment: string;
  endpoint?: string;
  sli_type: ApmSliType;
  objective: number | string;
  latency_threshold_ms?: number | null;
  evaluation_window: ApmSloEvaluationWindow;
  is_enabled: boolean;
}

export interface ApmSlo extends Omit<ApmSloInput, 'objective'> {
  id: string;
  objective: string;
  service_namespace: string;
  service_name: string;
  current_rate: number | null;
  budget_remaining: number | null;
  data_state: ApmMetricDataState;
  started_at: string | null;
  ended_at: string;
  reason?: string;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

export type ApmTopologyHealth = 'healthy' | 'warning' | 'critical' | 'unknown';

export type ApmTimeWindow = '15m' | '1h' | '4h' | '1d' | '7d';

export type ApmDashboardSectionStatus = 'ok' | 'failed' | 'empty';

export interface ApmDashboardSection<T> {
  status: ApmDashboardSectionStatus;
  data?: T;
  error?: string;
}

export interface ApmDashboardKpiData {
  application_count: number;
  service_count: number;
  active_alert_count: number;
  request_rate: number | null;
  error_request_rate: number | null;
  p95_ms: number | null;
  sparklines: {
    application_count: (number | null)[];
    service_count: (number | null)[];
    active_alert_count: (number | null)[];
    request_rate: (number | null)[];
    error_request_rate: (number | null)[];
    p95_ms: (number | null)[];
  };
}

export interface ApmDashboardHealthBucket {
  key: ApmTopologyHealth;
  label: string;
  count: number;
}

export interface ApmDashboardHealthData {
  total: number;
  buckets: ApmDashboardHealthBucket[];
}

export interface ApmDashboardAlertRow {
  id: string;
  service: string;
  service_id: string | null;
  name: string;
  severity: 'critical' | 'warning';
  environment: string;
  started_at: string;
}

export interface ApmDashboardSloRow {
  id: string;
  service_id: string;
  service_name: string;
  environment: string;
  objective: number;
  current_rate: number;
  met: boolean;
}

export interface ApmDashboardTopRow {
  service_id: string;
  service_name: string;
  environment: string;
  value: number;
  sub_value: number | null;
}

export type ApmDeploymentStatus = 'success' | 'in_progress' | 'rollback' | 'failed';
export type ApmDeploymentSource = 'inferred' | 'reported';

export interface ApmDeploymentEvent {
  id: string;
  service_id: string;
  service_namespace: string;
  service_name: string;
  environment: string;
  version: string;
  deployed_at: string;
  deployed_by: string;
  status: ApmDeploymentStatus;
  source: ApmDeploymentSource;
}

export interface ApmDashboardReleaseRow {
  id: string;
  service_id: string;
  service_name: string;
  environment: string;
  version: string;
  deployed_at: string;
  deployed_by: string;
  status: ApmDeploymentStatus;
  source?: ApmDeploymentSource;
}

export interface ApmDashboard {
  empty: boolean;
  window: ApmTimeWindow;
  kpis: ApmDashboardSection<ApmDashboardKpiData>;
  health: ApmDashboardSection<ApmDashboardHealthData>;
  slos: ApmDashboardSection<{ items: ApmDashboardSloRow[] }>;
  alerts: ApmDashboardSection<{ items: ApmDashboardAlertRow[] }>;
  top_error_rate: ApmDashboardSection<{ items: ApmDashboardTopRow[] }>;
  top_p95: ApmDashboardSection<{ items: ApmDashboardTopRow[] }>;
  releases: ApmDashboardSection<{ items: ApmDashboardReleaseRow[] }>;
}

export type ApmTopologyNodeKind = 'instrumented' | 'inferred';

export interface ApmTopologySampleTrace {
  trace_id: string;
  span_id: string;
  span_name: string;
  started_at: string;
  duration_ms: number;
  status: 'ok' | 'error';
  caller_service_name?: string;
  peer_address?: string;
  db_name?: string;
}

export interface ApmTopologyNode {
  id: string;
  service_namespace: string;
  service_name: string;
  environment: string;
  health: ApmTopologyHealth;
  sampled_spans: number;
  error_spans: number;
  language?: string;
  kind?: ApmTopologyNodeKind;
  fold_key?: string;
  inferred_system?: string;
  peer_address?: string;
  db_name?: string;
  request_rate?: number | null;
  error_rate?: number | null;
  p95_ms?: number | null;
  sample_traces?: ApmTopologySampleTrace[];
}

export interface ApmTopologyEdge {
  source: string;
  target: string;
  health: ApmTopologyHealth;
  sampled_calls: number;
  error_calls: number;
  average_duration_ms: number;
  p95_ms?: number | null;
  error_rate?: number | null;
  sample_traces?: ApmTopologySampleTrace[];
}

export interface ApmTopologyGraph {
  nodes: ApmTopologyNode[];
  edges: ApmTopologyEdge[];
  sampled_traces: number;
  truncated: boolean;
  data_state: 'available' | 'no_data';
  diagnostics?: string[];
}

export interface ApmApplication {
  id: string;
  application_id: string;
  name: string;
  description: string;
  is_builtin: boolean;
  service_count: number;
  organization_ids: number[];
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

export interface ApmApplicationInput {
  application_id?: string;
  name: string;
  description?: string;
  organization_ids: number[];
}

export interface ApmIngestSnippetInput {
  application_id: string;
  cloud_region_id: number;
  language: 'python' | 'nodejs' | 'java' | 'go';
  runtime: 'kubernetes' | 'docker' | 'host' | 'other';
  service_name: string;
  service_version?: string;
  environment: string;
}

export interface ApmCloudRegion {
  id: number;
  name: string;
}

export interface ApmIngestSnippet {
  application_id: string;
  application_name: string;
  cloud_region: ApmCloudRegion;
  http_endpoint: string;
  environment: Record<string, string>;
  code: string;
}

export interface ApmHealth {
  catalog_reconcile: ApmHealthComponent;
  regional_collector: ApmHealthComponent;
  nats_publish: ApmHealthComponent;
  jetstream: ApmHealthComponent;
  system_collector: ApmHealthComponent;
  victoria_traces: ApmHealthComponent;
  victoria_traces_retention: ApmHealthComponent;
  notification_responder: ApmHealthComponent;
  policy_evaluation: ApmHealthComponent;
  notification_delivery: ApmHealthComponent & { failed_deliveries?: number };
}

export interface ApmHealthComponent {
  status: 'pending' | 'ok' | 'degraded';
  last_succeeded_at?: string;
  last_failed_at?: string;
  last_checked_at?: string;
  error_code?: string;
  publish_acks?: number;
  last_publish_ack_at?: string;
  stream_bytes?: number;
  stream_messages?: number;
  capacity_percent?: number;
  queue_size?: number;
  queue_capacity?: number;
  queue_capacity_percent?: number;
  consumer_pending?: number;
  consumer_ack_pending?: number;
  consumer_redelivered?: number;
  configured_days?: number;
  required_days?: number;
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
  service_name?: string;
  environment?: string;
  instance_id?: string;
  span_name?: string;
  status?: 'ok' | 'error';
  min_duration_ms?: number;
  max_duration_ms?: number;
  started_at?: string;
  ended_at?: string;
  cursor?: string;
  limit?: number;
}

export interface ApmSpanSummary {
  trace_id: string;
  span_id: string;
  started_at: string;
  duration_ms: number;
  service_namespace: string;
  service_name: string;
  environment: string;
  instance_id: string | null;
  status: 'ok' | 'error';
  name: string;
  kind: string;
  http_method: string | null;
  http_status_code: string | null;
}

export interface ApmSpanPage {
  items: ApmSpanSummary[];
  next_cursor: string | null;
}

export interface ApmIssueDistribution {
  value: string;
  count: number;
  percent: number;
}

export interface ApmIssueSampleTrace {
  trace_id: string;
  span_id: string;
  endpoint: string;
  started_at: string;
  duration_ms: number;
}

export interface ApmIssue {
  fingerprint: string;
  exception_type: string;
  message: string;
  stacktrace: string;
  service_namespace: string;
  service_name: string;
  environment: string;
  occurrences: number;
  affected_traces: number;
  last_seen_at: string;
  version_distribution: ApmIssueDistribution[];
  endpoint_distribution: ApmIssueDistribution[];
  sample_traces: ApmIssueSampleTrace[];
}

export interface ApmIssuePage {
  items: ApmIssue[];
  next_cursor: string | null;
  truncated: boolean;
}

export interface ApmIssueSearchParams {
  service_namespace?: string;
  service_name?: string;
  environment?: string;
  started_at?: string;
  ended_at?: string;
  cursor?: string;
  limit?: number;
}

export interface ApmSpanSearchParams {
  service_namespace?: string;
  service_name?: string;
  environment?: string;
  instance_id?: string;
  span_name?: string;
  status?: 'ok' | 'error';
  kind?: 'internal' | 'server' | 'client' | 'producer' | 'consumer';
  min_duration_ms?: number;
  max_duration_ms?: number;
  started_at?: string;
  ended_at?: string;
  cursor?: string;
  limit?: number;
}

export type ApmPolicyMetric = 'error_rate' | 'p95' | 'p99' | 'throughput' | 'no_traffic';
export type ApmPolicyComparator = 'gt' | 'gte' | 'lt' | 'lte';
export type ApmPolicySeverity = 'critical' | 'error' | 'warning';
export type ApmPolicyAggregation = 'avg' | 'max' | 'min' | 'last';
export type ApmPolicyVersionMode = 'all' | 'specific' | 'grouped';
export type ApmNotificationDeliveryMode = 'message' | 'alert_event_copy';
export type ApmNotificationRecipientMode = 'none' | 'system_user' | 'free_text';

export interface ApmPolicyNotificationTarget {
  channel_id: number;
  channel_name?: string;
  channel_type?: string;
  delivery_mode?: ApmNotificationDeliveryMode;
  recipient_mode?: ApmNotificationRecipientMode;
  recipients: string[];
}

export interface ApmPolicyInput {
  name: string;
  service_id: string;
  environment: string;
  alert_name?: string;
  endpoints: string[];
  version_mode: ApmPolicyVersionMode;
  versions: string[];
  metric_type: ApmPolicyMetric;
  evaluation_interval: number;
  metric_window: number;
  aggregation: ApmPolicyAggregation;
  thresholds: Array<{ severity: ApmPolicySeverity; comparator: ApmPolicyComparator; value: number | string }>;
  trigger_after: number;
  recover_after: number;
  no_data_after?: number | null;
  no_data_severity?: ApmPolicySeverity | '';
  no_data_alert_name?: string;
  notification_targets: ApmPolicyNotificationTarget[];
  is_enabled?: boolean;
}

export interface ApmPolicy extends ApmPolicyInput {
  id: string;
  is_enabled: boolean;
  service_namespace: string;
  service_name: string;
  state: {
    status: 'normal' | 'active';
    consecutive_hits: number;
    consecutive_recoveries: number;
    last_succeeded_at: string | null;
    last_failed_at: string | null;
  } | null;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

export interface ApmPolicyQueryResult {
  value: string | null;
  breached: boolean | null;
  evaluated_at: string;
  data_state: 'available' | 'no_data';
  threshold: { severity: ApmPolicySeverity; comparator: ApmPolicyComparator; value: string } | null;
  series: Array<{
    timestamp: string;
    request_rate: number | null;
    error_rate: number | null;
    p95_ms: number | null;
    p99_ms: number | null;
  }>;
}

export interface ApmEvent {
  id: string;
  event_id: string;
  external_id: string;
  title: string;
  description: string;
  severity: ApmPolicySeverity | 'info';
  action: 'triggered' | 'escalated' | 'recovered' | 'closed';
  status: 'active' | 'recovered' | 'closed';
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
  notification_deliveries: ApmNotificationDelivery[];
  endpoint?: string;
  version?: string;
  snapshot_status?: ApmEventSnapshot['payload_status'];
}

export interface ApmEventQuery {
  action?: ApmEvent['action'];
  severity?: ApmPolicySeverity;
  started_at?: string;
  ended_at?: string;
  limit?: number;
}

export interface ApmAlertEvent {
  id: string;
  event_id: string;
  action: ApmEvent['action'];
  severity: ApmPolicySeverity;
  value: string | null;
  occurred_at: string;
  title: string;
  description: string;
}

export interface ApmAlert {
  id: string;
  external_id: string;
  title: string;
  policy_id: string;
  policy_name: string;
  service_id: string | null;
  service_namespace: string;
  service_name: string;
  environment: string;
  endpoint: string;
  version: string;
  metric_type: ApmPolicyMetric;
  severity: ApmPolicySeverity;
  status: 'active' | 'recovered' | 'closed';
  notification_status?: 'none' | 'pending' | 'delivered' | 'partial' | 'failed';
  current_value: string | null;
  operator: string;
  started_at: string;
  ended_at: string | null;
  last_event_at: string;
  event_count: number;
  events: ApmAlertEvent[];
}

export interface ApmAlertQuery {
  status?: ApmAlert['status'];
  status_group?: 'active' | 'history';
  severity?: ApmPolicySeverity;
  metric_type?: ApmPolicyMetric;
  service_id?: string;
  keyword?: string;
  started_at?: string;
  ended_at?: string;
  limit?: number;
}

export interface ApmAlertMetricSnapshotItem {
  type: 'event' | 'info' | 'no_data';
  snapshot_time: string;
  event_id: string | null;
  event_time: string | null;
  value: string | null;
  threshold: {
    severity: ApmPolicySeverity;
    comparator: ApmPolicyComparator | 'no_data';
    value: string | number;
  } | null;
  data_state: 'available' | 'no_data';
}

export interface ApmAlertMetricSnapshot {
  unit: string;
  aggregation: ApmPolicyAggregation;
  evaluation_interval: number;
  metric_window: number;
  snapshots: ApmAlertMetricSnapshotItem[];
}

export interface ApmEventSnapshot {
  id: string;
  event_id: string;
  schema_version: number;
  action: ApmEvent['action'];
  occurred_at: string;
  policy_snapshot: Record<string, unknown>;
  object_snapshot: Record<string, unknown>;
  evaluation_snapshot: {
    value: string | null;
    unit?: string;
    comparator?: ApmPolicyComparator | 'closed' | null;
    threshold?: string | null;
    severity?: ApmPolicySeverity;
    data_state: 'available' | 'no_data';
  };
  trace_context: Record<string, unknown>;
  payload_status: 'pending' | 'available' | 'unavailable' | 'expired';
  payload_error_code: string;
  payload: {
    event_point: string;
    threshold: { severity: ApmPolicySeverity; comparator: ApmPolicyComparator; value: string } | null;
    series: Array<{ timestamp: string; value: number | null }>;
  } | null;
  retention_expires_at: string;
}

export interface ApmNotificationChannel {
  id: number;
  name: string;
  channel_type: string;
  description: string;
  delivery_mode: ApmNotificationDeliveryMode;
  recipient_mode: ApmNotificationRecipientMode;
  availability: 'available' | 'unavailable';
}

export interface ApmNotificationRecipient {
  id: number;
  username: string;
  display_name: string;
}

export interface ApmNotificationDelivery {
  id: string;
  event_id: string | null;
  channel_id: number | null;
  channel_name: string;
  channel_type: string;
  delivery_mode: ApmNotificationDeliveryMode;
  recipients: string[];
  status: 'pending' | 'delivered' | 'failed';
  attempts: number;
  next_retry_at: string | null;
  last_error_code: string;
  last_error_message: string;
  delivered_at: string | null;
  failed_at: string | null;
}
