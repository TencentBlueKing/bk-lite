export type CatalogStatus = 'active' | 'silent' | 'archived';

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

export interface ApmTopologyNode {
  id: string;
  service_namespace: string;
  service_name: string;
  environment: string;
  health: ApmTopologyHealth;
  sampled_spans: number;
  error_spans: number;
}

export interface ApmTopologyEdge {
  source: string;
  target: string;
  health: ApmTopologyHealth;
  sampled_calls: number;
  error_calls: number;
  average_duration_ms: number;
}

export interface ApmTopologyGraph {
  nodes: ApmTopologyNode[];
  edges: ApmTopologyEdge[];
  sampled_traces: number;
  truncated: boolean;
  data_state: 'available' | 'no_data';
}

export interface ApmApplication {
  id: string;
  application_id: string;
  name: string;
  description: string;
  is_enabled: boolean;
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
  is_enabled?: boolean;
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
  grpc_endpoint: string;
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
  metric_type: ApmPolicyMetric;
  comparator: ApmPolicyComparator;
  threshold: number | string;
  duration_window: number;
  recovery_window: number;
  severity: ApmPolicySeverity;
  notification_targets: ApmPolicyNotificationTarget[];
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
  created_by: string;
  updated_by: string;
}

export interface ApmPolicyQueryResult {
  value: string | null;
  breached: boolean | null;
  evaluated_at: string;
  data_state: 'available' | 'no_data';
}

export interface ApmEvent {
  id: string;
  event_id: string;
  external_id: string;
  title: string;
  description: string;
  severity: ApmPolicySeverity | 'info';
  action: 'created' | 'recovery';
  status: 'firing' | 'recovered';
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
