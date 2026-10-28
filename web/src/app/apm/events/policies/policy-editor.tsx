'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { DeleteOutlined } from '@ant-design/icons';
import {
  Button,
  Form,
  Input,
  InputNumber,
  message,
  Popconfirm,
  Radio,
  Select,
  Space,
  Steps,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmPageBreadcrumb from '@/app/apm/components/apm-page-breadcrumb';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState from '@/app/apm/components/catalog-state';
import { formatClockTime, formatErrorRate } from '@/app/apm/components/metric-format';
import GroupTreeSelect from '@/components/group-tree-select';
import TimeSeriesComposedChart, {
  type TimeSeriesComposedChartSeries,
} from '@/components/time-series-composed-chart';
import { ALERT_LEVEL_COLORS, OBSERVABILITY_SERIES_COLORS } from '@/constants/observabilityChart';
import { useTranslation } from '@/utils/i18n';
import { HandledRequestError } from '@/utils/request';
import { formatUserName } from '@/utils/userDisplay';
import type {
  ApmCompareMode,
  ApmCompareValueKind,
  ApmNotificationChannel,
  ApmNotificationRecipient,
  ApmPolicy,
  ApmPolicyComparator,
  ApmPolicyDryRunResult,
  ApmPolicyInput,
  ApmPolicyMetric,
  ApmPolicyQueryResult,
  ApmPolicySeriesPoint,
  ApmPolicySeverity,
  ApmService,
} from '@/app/apm/types';
import styles from '@/app/apm/events/event-workspace.module.scss';
import NotificationTargetFields, {
  type NotificationDirectoryState,
} from '@/app/apm/events/policies/notification-target-fields';

interface ThresholdEditorRow {
  severity: ApmPolicySeverity;
  comparator: ApmPolicyComparator;
  value: number | null;
}

interface PolicyEditorValues extends Omit<
  ApmPolicyInput,
  'service_id' | 'environment' | 'version_mode' | 'versions' | 'thresholds' | 'organizations'
> {
  service_scope: string;
  organizations: number[];
  no_data_alert_name: string;
  handlers: Array<string | number>;
  thresholds: ThresholdEditorRow[];
  recovery_comparator: ApmPolicyComparator;
  recovery_value: number | null;
}

const SEVERITIES: Array<{ value: ApmPolicySeverity; i18nKey: string; color: string }> = [
  { value: 'critical', i18nKey: 'apm.severity.critical', color: 'red' },
  { value: 'error', i18nKey: 'apm.severity.error', color: 'orange' },
  { value: 'warning', i18nKey: 'apm.severity.warning', color: 'gold' },
];

const DEFAULT_VALUES: PolicyEditorValues = {
  name: '',
  service_scope: '',
  organizations: [],
  alert_name: '${service} ${metric} ${comparator} ${threshold}',
  endpoints: [],
  metric_type: 'error_rate',
  evaluation_interval: 1,
  metric_window: 5,
  aggregation: 'avg',
  compare_mode: 'absolute',
  compare_offset_amount: null,
  compare_value_kind: '',
  min_request_count: 20,
  thresholds: SEVERITIES.map(({ value }) => ({
    severity: value,
    comparator: 'gt',
    value: value === 'warning' ? 5 : null,
  })),
  trigger_after: 3,
  trigger_window: null,
  recovery_comparator: 'lt',
  recovery_value: null,
  recover_after: 3,
  no_data_after: null,
  no_data_severity: '',
  no_data_alert_name: '${service} ${metric}',
  handlers: [],
  notification_targets: [],
};

function directoryErrorState(error: unknown): NotificationDirectoryState {
  return error instanceof HandledRequestError && error.status === 403 ? 'forbidden' : 'error';
}

const METRIC_GROUPS: Array<{ labelKey: string; metrics: Array<{ value: ApmPolicyMetric; i18nKey: string }> }> = [
  {
    labelKey: 'apm.policies.metricGroupLatency',
    metrics: [
      { value: 'latency_avg', i18nKey: 'apm.policies.metricLatencyAvg' },
      { value: 'p50', i18nKey: 'apm.policies.metricP50' },
      { value: 'p75', i18nKey: 'apm.policies.metricP75' },
      { value: 'p90', i18nKey: 'apm.policies.metricP90' },
      { value: 'p95', i18nKey: 'apm.policies.metricP95' },
      { value: 'p99', i18nKey: 'apm.policies.metricP99' },
      { value: 'latency_max', i18nKey: 'apm.policies.metricLatencyMax' },
    ],
  },
  {
    labelKey: 'apm.policies.metricGroupErrors',
    metrics: [
      { value: 'error_rate', i18nKey: 'apm.common.errorRate' },
      { value: 'error_count', i18nKey: 'apm.policies.metricErrorCount' },
    ],
  },
  {
    labelKey: 'apm.policies.metricGroupSlow',
    metrics: [
      { value: 'slow_request_count', i18nKey: 'apm.policies.metricSlowCount' },
      { value: 'slow_request_rate', i18nKey: 'apm.policies.metricSlowRate' },
    ],
  },
  {
    labelKey: 'apm.policies.metricGroupApdex',
    metrics: [{ value: 'apdex', i18nKey: 'apm.policies.metricApdex' }],
  },
  {
    labelKey: 'apm.policies.metricGroupThroughput',
    metrics: [{ value: 'throughput', i18nKey: 'apm.common.throughput' }],
  },
  {
    labelKey: 'apm.policies.metricGroupTraffic',
    metrics: [{ value: 'no_traffic', i18nKey: 'apm.alerts.noTraffic' }],
  },
];

const METRICS: Array<{ value: ApmPolicyMetric; i18nKey: string }> = METRIC_GROUPS.flatMap((group) => group.metrics);

const VERDICT_KEY = {
  would_trigger: 'apm.policies.verdictWouldTrigger',
  ok: 'apm.policies.verdictOk',
  would_recover: 'apm.policies.verdictWouldRecover',
  would_escalate: 'apm.policies.verdictWouldEscalate',
  no_data: 'apm.policies.verdictNoData',
  missing_baseline: 'apm.policies.verdictMissingBaseline',
  insufficient_samples: 'apm.policies.verdictInsufficient',
  hold: 'apm.policies.verdictHold',
} as const;

const TEMPLATE_VARIABLES = [
  { name: '${service}', i18nKey: 'apm.policies.variableService' },
  { name: '${endpoint}', i18nKey: 'apm.policies.variableEndpoint' },
  { name: '${version}', i18nKey: 'apm.policies.variableVersion' },
  { name: '${metric}', i18nKey: 'apm.policies.variableMetric' },
  { name: '${current_value}', i18nKey: 'apm.policies.variableCurrentValue' },
  { name: '${threshold}', i18nKey: 'apm.policies.variableThreshold' },
  { name: '${level}', i18nKey: 'apm.policies.variableLevel' },
  { name: '${alert_name}', i18nKey: 'apm.policies.variableAlertName' },
  { name: '${trigger_at}', i18nKey: 'apm.policies.variableTriggeredAt' },
  { name: '${group_by}', i18nKey: 'apm.policies.variableGroupBy' },
];

function encodeServiceScope(serviceId: string, environment: string) {
  return `${serviceId}:${encodeURIComponent(environment)}`;
}

function decodeServiceScope(scope: string) {
  const separator = scope.indexOf(':');
  if (separator < 0) return { serviceId: scope, environment: '' };
  return {
    serviceId: scope.slice(0, separator),
    environment: decodeURIComponent(scope.slice(separator + 1)),
  };
}

const LATENCY_METRICS: ApmPolicyMetric[] = ['p50', 'p75', 'p90', 'p95', 'p99', 'latency_avg', 'latency_max'];
const RATIO_METRICS: ApmPolicyMetric[] = ['error_rate', 'slow_request_rate', 'apdex'];
const COUNT_METRICS: ApmPolicyMetric[] = ['error_count', 'slow_request_count'];
const SLOW_METRICS: ApmPolicyMetric[] = ['slow_request_count', 'slow_request_rate'];
const MIN_REQUEST_METRICS: ApmPolicyMetric[] = ['error_rate', 'slow_request_rate', 'apdex', ...LATENCY_METRICS];

function scalesStoredRatio(metric: ApmPolicyMetric, kind: ApmCompareValueKind | '') {
  return RATIO_METRICS.includes(metric) && kind !== 'percent';
}

function thresholdToEditorValue(
  metric: ApmPolicyMetric,
  kind: ApmCompareValueKind | '',
  value: number | string,
) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  return scalesStoredRatio(metric, kind) ? numeric * 100 : numeric;
}

function normalizeThresholds(
  metric: ApmPolicyMetric,
  kind: ApmCompareValueKind | '',
  rows: ThresholdEditorRow[] = [],
) {
  return rows.flatMap((item, index) => {
    if (item.value === null || item.value === undefined) return [];
    const numericValue = Number(item.value);
    if (!Number.isFinite(numericValue)) return [];
    return [{
      severity: item.severity ?? SEVERITIES[index].value,
      comparator: item.comparator,
      value: scalesStoredRatio(metric, kind) ? numericValue / 100 : numericValue,
    }];
  });
}

function resolvedCompareKind(
  metric: ApmPolicyMetric,
  mode: ApmCompareMode | undefined,
  kind: ApmCompareValueKind | '' | undefined,
): ApmCompareValueKind | '' {
  if (metric === 'no_traffic' || !mode || mode === 'absolute') return '';
  if (mode === 'previous_window' || mode === 'baseline_days') return kind === 'percent' ? 'percent' : 'delta';
  return 'percent';
}

const MAX_COMPARE_OFFSET_HOURS = 840;
const MAX_COMPARE_OFFSET_DAYS = 35;

function editorCompareState(policy: ApmPolicy): Pick<PolicyEditorValues, 'compare_mode' | 'compare_offset_amount'> {
  if (policy.compare_mode === 'offset_1h') return { compare_mode: 'offset_hours', compare_offset_amount: 1 };
  if (policy.compare_mode === 'offset_24h') return { compare_mode: 'offset_hours', compare_offset_amount: 24 };
  if (policy.compare_mode === 'offset_hours' || policy.compare_mode === 'offset_days') {
    return { compare_mode: policy.compare_mode, compare_offset_amount: policy.compare_offset_amount ?? 1 };
  }
  if (policy.compare_mode === 'baseline_days') {
    return { compare_mode: 'baseline_days', compare_offset_amount: policy.compare_offset_amount ?? 7 };
  }
  return { compare_mode: policy.compare_mode ?? 'absolute', compare_offset_amount: null };
}

function comparePayloadFields(values: PolicyEditorValues): Partial<ApmPolicyInput> {
  if (values.metric_type === 'no_traffic') return {};
  const compareMode = values.compare_mode || 'absolute';
  const compareKind = resolvedCompareKind(values.metric_type, compareMode, values.compare_value_kind);
  const offset = compareMode === 'offset_hours' || compareMode === 'offset_days' || compareMode === 'baseline_days';
  const fields: Partial<ApmPolicyInput> = {
    compare_mode: compareMode,
    compare_offset_amount: offset ? values.compare_offset_amount ?? null : null,
    compare_value_kind: compareKind,
  };
  if (MIN_REQUEST_METRICS.includes(values.metric_type)) {
    fields.min_request_count = values.min_request_count ?? null;
  } else {
    fields.min_request_count = null;
  }
  return fields;
}

function metricParamFields(values: PolicyEditorValues): Partial<ApmPolicyInput> {
  if (values.metric_type === 'no_traffic') {
    const cleared: Partial<ApmPolicyInput> = {};
    if (values.slow_threshold_ms != null) cleared.slow_threshold_ms = null;
    if (values.apdex_threshold_ms != null) cleared.apdex_threshold_ms = null;
    return cleared;
  }
  return {
    slow_threshold_ms: SLOW_METRICS.includes(values.metric_type) ? values.slow_threshold_ms ?? null : null,
    apdex_threshold_ms: values.metric_type === 'apdex' ? values.apdex_threshold_ms ?? 500 : null,
  };
}

function judgmentFields(values: PolicyEditorValues): Partial<ApmPolicyInput> {
  const kind = resolvedCompareKind(values.metric_type, values.compare_mode, values.compare_value_kind);
  const recovery: NonNullable<ApmPolicyInput['recovery_threshold']> = values.recovery_value === null || values.recovery_value === undefined
    ? {}
    : {
      comparator: values.recovery_comparator,
      value: scalesStoredRatio(values.metric_type, kind) ? Number(values.recovery_value) / 100 : Number(values.recovery_value),
    };
  if (values.metric_type === 'no_traffic') {
    const cleared: Partial<ApmPolicyInput> = {};
    if (values.trigger_window != null) cleared.trigger_window = null;
    if (values.recovery_value != null) cleared.recovery_threshold = {};
    return cleared;
  }
  return {
    trigger_window: values.trigger_window ?? null,
    recovery_threshold: recovery,
  };
}

function seriesPointValue(metric: ApmPolicyMetric, point: ApmPolicySeriesPoint | undefined) {
  if (!point) return null;
  if (metric === 'error_rate') return point.error_rate == null ? null : Number(point.error_rate) * 100;
  if (metric === 'slow_request_rate') {
    if (point.slow_count == null || !point.request_count) return null;
    return (Number(point.slow_count) / Number(point.request_count)) * 100;
  }
  if (metric === 'apdex') {
    if (point.satisfied_count == null || point.tolerating_count == null || !point.request_count) return null;
    return ((Number(point.satisfied_count) + Number(point.tolerating_count) / 2) / Number(point.request_count)) * 100;
  }
  if (metric === 'error_count') return point.error_count ?? null;
  if (metric === 'slow_request_count') return point.slow_count ?? null;
  if (metric === 'p50') return point.p50_ms ?? null;
  if (metric === 'p75') return point.p75_ms ?? null;
  if (metric === 'p90') return point.p90_ms ?? null;
  if (metric === 'p95') return point.p95_ms;
  if (metric === 'p99') return point.p99_ms;
  if (metric === 'latency_avg') return point.avg_ms ?? null;
  if (metric === 'latency_max') return point.max_ms ?? null;
  return point.request_rate;
}

function MetricTypeSelect({
  id,
  value,
  onChange,
  onMetricChange,
}: {
  id?: string;
  value?: ApmPolicyMetric;
  onChange?: (value: ApmPolicyMetric) => void;
  onMetricChange?: (value: ApmPolicyMetric) => void;
}) {
  const { t } = useTranslation();
  return (
    <Select
      id={id}
      virtual={false}
      value={value}
      onChange={(next: ApmPolicyMetric) => {
        onChange?.(next);
        onMetricChange?.(next);
      }}
      options={METRIC_GROUPS.map((group) => ({
        label: t(group.labelKey),
        options: group.metrics.map((item) => ({ value: item.value, label: t(item.i18nKey) })),
      }))}
    />
  );
}

function CompareBaselineSelect({
  id,
  value,
  onChange,
  onModeChange,
}: {
  id?: string;
  value?: ApmCompareMode;
  onChange?: (value: ApmCompareMode) => void;
  onModeChange?: (value: ApmCompareMode, previous?: ApmCompareMode) => void;
}) {
  const { t } = useTranslation();
  const family: ApmCompareMode = value === 'offset_hours' || value === 'offset_days' || value === 'offset_1h' || value === 'offset_24h'
    ? 'offset_hours'
    : (value || 'absolute');
  return (
    <Select
      id={id}
      value={family}
      onChange={(next: ApmCompareMode) => {
        const previous = value;
        onChange?.(next);
        onModeChange?.(next, previous);
      }}
      options={[
        { value: 'absolute', label: t('apm.policies.compareModeAbsolute', '当前值') },
        { value: 'previous_window', label: t('apm.policies.compareModePreviousWindow', '相对上一等长窗') },
        { value: 'offset_hours', label: t('apm.policies.compareModeOffset', '同窗') },
        { value: 'baseline_days', label: t('apm.policies.compareModeBaselineDays', '近 N 天同窗均值') },
      ]}
    />
  );
}

function NumberWithUnit({ unit, ...props }: ComponentProps<typeof InputNumber<number>> & { unit: string }) {
  return (
    <Space.Compact className={styles.numberWithUnit}>
      <InputNumber<number> {...props} />
      <span className={styles.numberUnit}>{unit}</span>
    </Space.Compact>
  );
}

function toEditorValues(policy: ApmPolicy, defaultNoDataAlertName: string): PolicyEditorValues {
  const thresholds = new Map(policy.thresholds.map((item) => [item.severity, item]));
  const commonComparator = policy.thresholds[0]?.comparator ?? 'gt';
  return {
    name: policy.name,
    service_scope: encodeServiceScope(policy.service_id, policy.environment),
    organizations: policy.organizations || [],
    alert_name: policy.alert_name,
    metric_type: policy.metric_type,
    evaluation_interval: policy.evaluation_interval,
    metric_window: policy.metric_window,
    aggregation: policy.aggregation,
    ...editorCompareState(policy),
    compare_value_kind: policy.compare_value_kind ?? '',
    min_request_count: policy.min_request_count ?? null,
    slow_threshold_ms: policy.slow_threshold_ms ?? null,
    apdex_threshold_ms: policy.apdex_threshold_ms ?? null,
    thresholds: SEVERITIES.map(({ value: severity }) => {
      const threshold = thresholds.get(severity);
      const kind = resolvedCompareKind(policy.metric_type, policy.compare_mode, policy.compare_value_kind);
      return {
        severity,
        comparator: threshold?.comparator ?? commonComparator,
        value: threshold ? thresholdToEditorValue(policy.metric_type, kind, threshold.value) : null,
      };
    }),
    trigger_after: policy.trigger_after,
    trigger_window: policy.trigger_window ?? null,
    recovery_comparator: policy.recovery_threshold && 'comparator' in policy.recovery_threshold
      ? policy.recovery_threshold.comparator
      : 'lt',
    recovery_value: policy.recovery_threshold && 'value' in policy.recovery_threshold
      ? thresholdToEditorValue(
        policy.metric_type,
        resolvedCompareKind(policy.metric_type, policy.compare_mode, policy.compare_value_kind),
        policy.recovery_threshold.value,
      )
      : null,
    recover_after: policy.recover_after,
    no_data_after: policy.no_data_after,
    no_data_severity: policy.no_data_severity,
    no_data_alert_name: policy.no_data_alert_name || defaultNoDataAlertName,
    endpoints: policy.endpoints,
    handlers: policy.handlers || [],
    notification_targets: policy.notification_targets.map((target) => ({
      channel_id: target.channel_id,
      recipients: target.recipient_mode === 'none' ? [] : [...target.recipients],
    })),
  };
}

function buildMetricPreviewPayload(
  values: PolicyEditorValues,
  loadedPolicy: ApmPolicy | null,
  previewName: string,
): ApmPolicyInput | null {
  const scope = decodeServiceScope(values.service_scope ?? '');
  const compareKind = resolvedCompareKind(values.metric_type, values.compare_mode, values.compare_value_kind);
  const thresholds = normalizeThresholds(values.metric_type, compareKind, values.thresholds);
  if (
    !scope.serviceId
    || !scope.environment
    || !values.metric_type
    || !values.metric_window
    || !values.aggregation
    || !thresholds.length
  ) return null;
  const originalScope = loadedPolicy
    ? encodeServiceScope(loadedPolicy.service_id, loadedPolicy.environment)
    : null;
  const preserveLegacyScope = Boolean(loadedPolicy && values.service_scope === originalScope);
  return {
    name: values.name?.trim() || previewName,
    service_id: scope.serviceId,
    organizations: values.organizations || [],
    environment: scope.environment,
    alert_name: values.alert_name || '',
    endpoints: values.endpoints || [],
    version_mode: preserveLegacyScope ? loadedPolicy?.version_mode ?? 'all' : 'all',
    versions: preserveLegacyScope ? loadedPolicy?.versions ?? [] : [],
    metric_type: values.metric_type,
    evaluation_interval: values.evaluation_interval || 1,
    metric_window: values.metric_window,
    aggregation: COUNT_METRICS.includes(values.metric_type) ? 'avg' : values.aggregation,
    ...comparePayloadFields(values),
    ...metricParamFields(values),
    ...judgmentFields(values),
    thresholds,
    trigger_after: values.trigger_after || 1,
    recover_after: values.recover_after || 1,
    no_data_after: null,
    no_data_severity: '',
    no_data_alert_name: '',
    notification_targets: [],
  };
}

export default function ApmPolicyEditor({ policyId }: { policyId?: string }) {
  const { t } = useTranslation();
  const router = useRouter();
  const defaultNoDataAlertName = `${'${service}'} ${'${metric}'} ${t('apm.policies.noDataAlertSuffix', '无数据告警')}`;
  const defaultNoDataAlertNameRef = useRef(defaultNoDataAlertName);
  const severityOptions = useMemo(
    () => SEVERITIES.map((item) => ({ ...item, label: t(item.i18nKey) })),
    [t],
  );
  const metricOptions = useMemo(
    () => METRICS.map((item) => ({ ...item, label: t(item.i18nKey) })),
    [t],
  );
  const templateVariables = useMemo(
    () => TEMPLATE_VARIABLES.map((item) => ({ ...item, source: t(item.i18nKey) })),
    [t],
  );
  const {
    createPolicy,
    deletePolicy,
    getNotificationChannels,
    getNotificationRecipients,
    getPolicy,
    getServiceRed,
    getServices,
    isLoading,
    previewPolicy,
    dryRunPolicy,
    updatePolicy,
  } = useApmApi();
  const [form] = Form.useForm<PolicyEditorValues>();
  const serviceScope = Form.useWatch('service_scope', form);
  const metricType = Form.useWatch('metric_type', form) ?? 'error_rate';
  const compareMode = Form.useWatch('compare_mode', form) ?? 'absolute';
  const compareOffsetAmount = Form.useWatch('compare_offset_amount', form);
  const compareKindRaw = Form.useWatch('compare_value_kind', form) ?? '';
  const minRequestCount = Form.useWatch('min_request_count', form);
  const evaluationInterval = Form.useWatch('evaluation_interval', form);
  const metricWindow = Form.useWatch('metric_window', form);
  const aggregation = Form.useWatch('aggregation', form);
  const watchedThresholds = Form.useWatch('thresholds', form);
  const triggerWindow = Form.useWatch('trigger_window', form);
  const selectedEndpoints = Form.useWatch('endpoints', form);
  const noDataSeverity = Form.useWatch('no_data_severity', form);
  const notificationTargets = Form.useWatch('notification_targets', form) ?? [];
  const organizations = Form.useWatch('organizations', form);
  const selectedHandlers = Form.useWatch('handlers', form);
  const organizationKey = (organizations || []).join(',');
  const policyName = Form.useWatch('name', form);
  const [services, setServices] = useState<ApmService[]>([]);
  const [channels, setChannels] = useState<ApmNotificationChannel[]>([]);
  const [recipients, setRecipients] = useState<ApmNotificationRecipient[]>([]);
  const [channelState, setChannelState] = useState<NotificationDirectoryState>('loading');
  const [recipientState, setRecipientState] = useState<NotificationDirectoryState>('loading');
  const [availableEndpoints, setAvailableEndpoints] = useState<string[]>([]);
  const [loadedPolicy, setLoadedPolicy] = useState<ApmPolicy | null>(null);
  const [preview, setPreview] = useState<ApmPolicyQueryResult | null>(null);
  const [triggerMode, setTriggerMode] = useState<'consecutive' | 'window'>('consecutive');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewFailed, setPreviewFailed] = useState(false);
  const [dryRun, setDryRun] = useState<ApmPolicyDryRunResult | null>(null);
  const [dryRunning, setDryRunning] = useState(false);
  const [noticeEnabled, setNoticeEnabled] = useState(false);
  const [handlerUsers, setHandlerUsers] = useState<ApmNotificationRecipient[]>([]);
  const [directoriesRefreshing, setDirectoriesRefreshing] = useState(false);
  const previewRequestRef = useRef(0);
  const previewDebounceRef = useRef<number | null>(null);
  const recipientSearchRequestRef = useRef(0);
  const recipientSearchDebounceRef = useRef<number | null>(null);

  const loadNotificationDirectories = useCallback(async () => {
    const recipientRequestId = recipientSearchRequestRef.current + 1;
    recipientSearchRequestRef.current = recipientRequestId;
    setDirectoriesRefreshing(true);
    setChannelState('loading');
    setRecipientState('loading');
    const [channelResult, recipientResult] = await Promise.allSettled([
      getNotificationChannels(),
      getNotificationRecipients({ limit: 100 }),
    ]);
    if (channelResult.status === 'fulfilled') {
      setChannels(channelResult.value);
      setChannelState(channelResult.value.length ? 'ready' : 'empty');
    } else {
      setChannels([]);
      setChannelState(directoryErrorState(channelResult.reason));
    }
    if (recipientSearchRequestRef.current === recipientRequestId) {
      if (recipientResult.status === 'fulfilled') {
        setRecipients(recipientResult.value);
        setRecipientState(recipientResult.value.length ? 'ready' : 'empty');
      } else {
        setRecipients([]);
        setRecipientState(directoryErrorState(recipientResult.reason));
      }
    }
    setDirectoriesRefreshing(false);
  }, [getNotificationChannels, getNotificationRecipients]);

  const searchRecipients = useCallback(async (search: string) => {
    const requestId = recipientSearchRequestRef.current + 1;
    recipientSearchRequestRef.current = requestId;
    setRecipientState('loading');
    try {
      const items = await getNotificationRecipients({ search, limit: 100 });
      if (recipientSearchRequestRef.current !== requestId) return;
      setRecipients(items);
      setRecipientState(items.length ? 'ready' : 'empty');
    } catch (error) {
      if (recipientSearchRequestRef.current !== requestId) return;
      setRecipients([]);
      setRecipientState(directoryErrorState(error));
    }
  }, [getNotificationRecipients]);

  const scheduleRecipientSearch = useCallback((search: string) => {
    if (recipientSearchDebounceRef.current !== null) {
      window.clearTimeout(recipientSearchDebounceRef.current);
    }
    recipientSearchDebounceRef.current = window.setTimeout(() => {
      void searchRecipients(search.trim());
    }, 300);
  }, [searchRecipients]);

  useEffect(() => () => {
    if (recipientSearchDebounceRef.current !== null) {
      window.clearTimeout(recipientSearchDebounceRef.current);
    }
  }, []);

  useEffect(() => {
    if (loading) return;
    // rc-field-form 的 errors 和 warnings 初始指向同一个空数组。字段第一次
    // onChange 会把这份 meta 存进缓存，下一次 setFieldValue 再深比较时就会
    // 报 “There may be circular references”，开发态遮罩会挡住整页。
    // 挂载后用两份独立空数组写入缓存，后续切换比较基准不再误报。
    (['compare_mode', 'compare_value_kind', 'compare_offset_amount', 'recovery_comparator', 'thresholds', 'apdex_threshold_ms'] as const)
      .forEach((name) => form.setFieldValue(name, form.getFieldValue(name)));
  }, [form, loading]);

  useEffect(() => {
    if (isLoading) return;
    setLoading(true);
    Promise.all([
      getServices({ include_archived: true }),
      policyId ? getPolicy(policyId) : Promise.resolve(null),
    ])
      .then(([serviceItems, policy]) => {
        setServices(serviceItems);
        setLoadedPolicy(policy);
        setNoticeEnabled(Boolean(policy?.notification_targets.length));
        form.setFieldsValue(policy
          ? toEditorValues(policy, defaultNoDataAlertNameRef.current)
          : { ...DEFAULT_VALUES, no_data_alert_name: defaultNoDataAlertNameRef.current });
        setTriggerMode(policy?.trigger_window ? 'window' : 'consecutive');
      })
      .finally(() => setLoading(false));
    void loadNotificationDirectories();
  }, [form, getPolicy, getServices, isLoading, loadNotificationDirectories, policyId]);

  useEffect(() => {
    const orgIds = organizationKey
      ? organizationKey.split(',').map((item) => Number(item)).filter((item) => Number.isInteger(item) && item > 0)
      : [];
    if (!orgIds.length) {
      const formOrganizations = form.getFieldValue('organizations') || [];
      if (Array.isArray(formOrganizations) && formOrganizations.length) {
        return;
      }
      setHandlerUsers((prev) => (prev.length ? [] : prev));
      const current = form.getFieldValue('handlers') || [];
      if (Array.isArray(current) && current.length) {
        form.setFieldValue('handlers', []);
      }
      return;
    }
    let cancelled = false;
    void getNotificationRecipients({ organization_ids: orgIds.join(','), limit: 100 })
      .then((users) => {
        if (cancelled) return;
        const list = Array.isArray(users) ? users : [];
        setHandlerUsers((prev) => {
          if (
            prev.length === list.length
            && prev.every((item, index) => item.id === list[index]?.id)
          ) {
            return prev;
          }
          return list;
        });
      })
      .catch(() => {
        // 拉取失败时不改动已选处理人，避免误清空
      });
    return () => {
      cancelled = true;
    };
  }, [form, getNotificationRecipients, organizationKey]);

  useEffect(() => {
    const scope = decodeServiceScope(serviceScope ?? '');
    if (!scope.serviceId || !scope.environment) {
      setAvailableEndpoints([]);
      return;
    }
    let active = true;
    const endedAt = dayjs();
    void getServiceRed(
      scope.serviceId,
      scope.environment,
      endedAt.subtract(1, 'hour').toISOString(),
      endedAt.toISOString(),
    )
      .then((result) => {
        if (active) setAvailableEndpoints(result.top_endpoints.map((item) => item.endpoint));
      })
      .catch(() => {
        if (active) setAvailableEndpoints([]);
      });
    return () => {
      active = false;
    };
  }, [getServiceRed, serviceScope]);

  const serviceOptions = useMemo(() => {
    const activeOptions = services
      .filter((item) => !item.archived_at)
      .flatMap((item) => {
        const environments = item.environment_views?.filter((view) => view.environment) ?? [];
        return environments.map((view) => ({
          value: encodeServiceScope(item.id, view.environment),
          label: `${item.namespace ? `${item.namespace} / ` : ''}${item.name}${
            environments.length > 1 ? ` · ${view.environment}` : ''
          }`,
        }));
      });
    const loadedScope = loadedPolicy
      ? encodeServiceScope(loadedPolicy.service_id, loadedPolicy.environment)
      : null;
    if (!loadedPolicy || activeOptions.some((item) => item.value === loadedScope)) return activeOptions;
    const selectedService = services.find((item) => item.id === loadedPolicy.service_id);
    const selectedName = selectedService?.namespace
      ? `${selectedService.namespace} / ${selectedService.name}`
      : selectedService?.name || `${loadedPolicy.service_namespace} / ${loadedPolicy.service_name}`;
    return [
      ...activeOptions,
      {
        value: loadedScope,
        label: t('apm.policies.archivedServiceOption', '{name}（已归档）', { name: selectedName }),
        disabled: true,
      },
    ];
  }, [loadedPolicy, services, t]);

  const endpointOptions = useMemo(
    () => Array.from(new Set([...(selectedEndpoints || []), ...availableEndpoints])).map((endpoint) => ({
      value: endpoint,
      label: endpoint,
    })),
    [availableEndpoints, selectedEndpoints],
  );

  const handlerOptions = useMemo(() => {
    const options: Array<{ value: string | number; label: string }> = handlerUsers.map((item) => ({
      value: item.id,
      label: formatUserName(item),
    }));
    for (const id of selectedHandlers || []) {
      if (options.some((item) => String(item.value) === String(id))) continue;
      options.push({
        value: id,
        label: String(id),
      });
    }
    return options;
  }, [handlerUsers, selectedHandlers]);

  const channelById = useMemo(() => {
    const map = new Map<number, ApmNotificationChannel>();
    channels.forEach((item) => map.set(item.id, item));
    (loadedPolicy?.notification_targets || []).forEach((item) => {
      if (map.has(item.channel_id)) return;
      map.set(item.channel_id, {
        id: item.channel_id,
        name: item.channel_name || t('apm.alerts.channel', '渠道 {id}', { id: item.channel_id }),
        channel_type: item.channel_type || '',
        description: '',
        delivery_mode: item.delivery_mode || 'message',
        recipient_mode: item.recipient_mode || 'free_text',
        availability: 'unavailable',
      });
    });
    return map;
  }, [channels, loadedPolicy, t]);

  const availableChannelsToAdd = channels.filter(
    (channel) => channel.availability === 'available'
      && !notificationTargets.some((target) => target.channel_id === channel.id),
  );

  const selectedScope = decodeServiceScope(serviceScope ?? '');
  const compareKind = resolvedCompareKind(metricType, compareMode, compareKindRaw);
  const showCompare = metricType !== 'no_traffic';
  const showMinRequest = MIN_REQUEST_METRICS.includes(metricType);
  const showAggregation = !COUNT_METRICS.includes(metricType);
  const showSlowThreshold = SLOW_METRICS.includes(metricType);
  const showApdexThreshold = metricType === 'apdex';
  const ratioMetric = RATIO_METRICS.includes(metricType);
  const thresholdUnit = compareKind === 'percent'
    ? t('apm.common.percentUnit', '%')
    : ratioMetric && compareKind === 'delta'
      ? t('apm.policies.percentagePointUnit', '个百分点')
      : ratioMetric
        ? t('apm.common.percentUnit', '%')
        : LATENCY_METRICS.includes(metricType)
          ? t('apm.common.millisecondUnit', 'ms')
          : COUNT_METRICS.includes(metricType)
            ? t('apm.policies.timesUnit', '次')
            : t('apm.policies.perSecondUnit', 'req/s');
  const thresholdBounds = compareKind === 'percent' || compareKind === 'delta'
    ? (ratioMetric && compareKind === 'delta' ? { min: -100, max: 100 } : {})
    : ratioMetric
      ? { min: 0, max: 100 }
      : { min: 0 };
  const ladderComparator = (watchedThresholds || []).find((row) => row?.comparator)?.comparator || 'gt';
  const recoveryOptions: { value: ApmPolicyComparator; label: string }[] = ladderComparator === 'lt' || ladderComparator === 'lte'
    ? [{ value: 'gt', label: '>' }, { value: 'gte', label: '≥' }]
    : [{ value: 'lt', label: '<' }, { value: 'lte', label: '≤' }];
  const comparatorOptions = metricType === 'apdex' && compareKind === ''
    ? [{ value: 'lt' as const, label: '<' }, { value: 'lte' as const, label: '≤' }]
    : [
      { value: 'gt' as const, label: '>' },
      { value: 'gte' as const, label: '≥' },
      { value: 'lt' as const, label: '<' },
      { value: 'lte' as const, label: '≤' },
    ];
  const previewRows = useMemo(
    () => {
      const baselineSeries = preview?.baseline_series ?? [];
      return (preview?.series ?? []).map((point, index) => ({
        timestamp: point.timestamp,
        value: seriesPointValue(metricType, point),
        baseline: compareKind ? seriesPointValue(metricType, baselineSeries[index]) : null,
        threshold: preview?.threshold
          ? thresholdToEditorValue(metricType, compareKind, preview.threshold.value)
          : null,
      }));
    },
    [compareKind, metricType, preview],
  );
  const previewSeries = useMemo(() => {
    const rows: Array<TimeSeriesComposedChartSeries<(typeof previewRows)[number]>> = [
      {
        name: metricOptions.find((item) => item.value === metricType)?.label ?? metricType,
        type: 'line',
        dataKey: 'value',
        color: OBSERVABILITY_SERIES_COLORS[0],
        showArea: true,
        areaOpacity: 0.36,
        smooth: false,
        lineWidth: 1,
      },
    ];
    if (compareKind) {
      rows.push({
        name: t('apm.policies.previewBaselineSeries', '对照'),
        type: 'line',
        dataKey: 'baseline',
        color: OBSERVABILITY_SERIES_COLORS[1],
        lineType: 'dashed',
        lineWidth: 1,
      });
    }
    rows.push({
      name: t('apm.policies.currentThreshold', '当前阈值'),
      type: 'line',
      dataKey: 'threshold',
      color: ALERT_LEVEL_COLORS[preview?.threshold?.severity ?? 'critical'],
      lineWidth: 1,
    });
    return rows;
  }, [compareKind, metricOptions, metricType, preview?.threshold?.severity, t]);
  const previewConfiguration = JSON.stringify({
    serviceScope,
    endpoints: selectedEndpoints || [],
    metricType,
    evaluationInterval,
    metricWindow,
    aggregation,
    compareMode,
    compareOffsetAmount,
    compareKind,
    minRequestCount,
    thresholds: watchedThresholds || [],
  });

  const buildPayload = (values: PolicyEditorValues): ApmPolicyInput | null => {
    const scope = decodeServiceScope(values.service_scope);
    const compareKind = resolvedCompareKind(values.metric_type, values.compare_mode, values.compare_value_kind);
    const thresholds = normalizeThresholds(values.metric_type, compareKind, values.thresholds);
    if (!thresholds.length) {
      const error = t('apm.policies.thresholdRequiredOne', '至少启用一个告警级别');
      form.setFields([{ name: ['thresholds', 2, 'value'], errors: [error] }]);
      message.error(error);
      return null;
    }
    if (noticeEnabled && !values.notification_targets?.length) {
      message.error(t('apm.policies.channelRequiredWhenEnabled', '启用通知后请至少选择一个通知渠道'));
      return null;
    }
    if (noticeEnabled) {
      for (const target of values.notification_targets || []) {
        const channel = channelById.get(target.channel_id);
        if (
          (channelState === 'ready' || channelState === 'empty')
          && (!channel || channel.availability !== 'available')
        ) {
          message.error(t('apm.policies.invalidRemove', '已失效，保存前请移除'));
          return null;
        }
        if (channel?.recipient_mode !== 'none' && !target.recipients?.length) {
          message.error(t('apm.policies.recipientsRequiredForChannel', '所选通知渠道需要配置通知对象'));
          return null;
        }
      }
    }
    const originalScope = loadedPolicy
      ? encodeServiceScope(loadedPolicy.service_id, loadedPolicy.environment)
      : null;
    const preserveLegacyScope = Boolean(loadedPolicy && values.service_scope === originalScope);
    return {
      name: values.name,
      service_id: scope.serviceId,
      organizations: values.organizations || [],
      environment: scope.environment,
      alert_name: values.alert_name,
      endpoints: values.endpoints,
      version_mode: preserveLegacyScope ? loadedPolicy?.version_mode ?? 'all' : 'all',
      versions: preserveLegacyScope ? loadedPolicy?.versions ?? [] : [],
      metric_type: values.metric_type,
      evaluation_interval: values.evaluation_interval,
      metric_window: values.metric_window,
      aggregation: COUNT_METRICS.includes(values.metric_type) ? 'avg' : values.aggregation,
      ...comparePayloadFields(values),
      ...metricParamFields(values),
      ...judgmentFields(values),
      thresholds,
      trigger_after: values.trigger_after,
      recover_after: values.recover_after,
      no_data_after: values.no_data_after,
      no_data_severity: values.no_data_severity,
      no_data_alert_name: values.no_data_severity ? values.no_data_alert_name : '',
      handlers: values.handlers || [],
      notification_targets: noticeEnabled
        ? values.notification_targets.map((target) => ({
          channel_id: target.channel_id,
          recipients: channelById.get(target.channel_id)?.recipient_mode === 'none'
            ? []
            : target.recipients,
        }))
        : [],
    };
  };

  useEffect(() => {
    if (loading) return;
    const payload = buildMetricPreviewPayload(
      form.getFieldsValue(true),
      loadedPolicy,
      t('apm.policies.metricPreview', '指标预览'),
    );
    if (previewDebounceRef.current !== null) window.clearTimeout(previewDebounceRef.current);
    if (!payload) {
      previewRequestRef.current += 1;
      setPreview(null);
      setPreviewing(false);
      setPreviewFailed(false);
      return;
    }
    previewDebounceRef.current = window.setTimeout(() => {
      const requestId = previewRequestRef.current + 1;
      previewRequestRef.current = requestId;
      setPreviewing(true);
      setPreviewFailed(false);
      void previewPolicy(payload, true)
        .then((result) => {
          if (previewRequestRef.current === requestId) setPreview(result);
        })
        .catch(() => {
          if (previewRequestRef.current === requestId) {
            setPreview(null);
            setPreviewFailed(true);
          }
        })
        .finally(() => {
          if (previewRequestRef.current === requestId) setPreviewing(false);
        });
    }, 500);
    return () => {
      if (previewDebounceRef.current !== null) window.clearTimeout(previewDebounceRef.current);
      previewRequestRef.current += 1;
    };
  }, [form, loadedPolicy, loading, previewConfiguration, previewPolicy, t]);

  const submit = async (values: PolicyEditorValues) => {
    const payload = buildPayload(values);
    if (!payload) return;
    setSaving(true);
    try {
      if (policyId) await updatePolicy(policyId, payload);
      else await createPolicy(payload);
      message.success(
        policyId
          ? t('apm.policies.updatedDetail', '策略已更新；后续评估使用新配置，历史快照保持不变')
          : t('apm.policies.createdDetail', '策略已创建；后续启停只在列表操作'),
      );
      router.push('/apm/events/policies');
    } finally {
      setSaving(false);
    }
  };

  const runPreview = async () => {
    const payload = buildMetricPreviewPayload(
      form.getFieldsValue(true),
      loadedPolicy,
      t('apm.policies.metricPreview', '指标预览'),
    );
    if (!payload) {
      message.info(t('apm.policies.previewPrerequisite', '请先选择服务并至少启用一个告警阈值'));
      return;
    }
    if (previewDebounceRef.current !== null) window.clearTimeout(previewDebounceRef.current);
    const requestId = previewRequestRef.current + 1;
    previewRequestRef.current = requestId;
    setPreviewing(true);
    setPreviewFailed(false);
    try {
      const result = await previewPolicy(payload);
      if (previewRequestRef.current === requestId) setPreview(result);
    } catch {
      if (previewRequestRef.current === requestId) setPreviewFailed(true);
    } finally {
      if (previewRequestRef.current === requestId) setPreviewing(false);
    }
  };

  const applyMetric = (metric: ApmPolicyMetric) => {
    if (metric === 'apdex' && form.getFieldValue('apdex_threshold_ms') == null) {
      form.setFieldValue('apdex_threshold_ms', 500);
    }
    if (metric === 'apdex') {
      const rows = (form.getFieldValue('thresholds') || []) as ThresholdEditorRow[];
      form.setFieldValue('thresholds', rows.map((row) => (
        row.comparator === 'gt' || row.comparator === 'gte' ? { ...row, comparator: 'lt' } : row
      )));
      const recovery = form.getFieldValue('recovery_comparator') as ApmPolicyComparator | undefined;
      if (recovery === 'lt' || recovery === 'lte') {
        form.setFieldValue('recovery_comparator', recovery === 'lte' ? 'gte' : 'gt');
      }
    }
  };

  const applyCompareMode = (mode: ApmCompareMode, previous?: ApmCompareMode) => {
    if (mode === 'absolute') {
      form.setFieldValue('compare_value_kind', '');
      form.setFieldValue('compare_offset_amount', null);
      return;
    }
    if (mode === 'previous_window') {
      form.setFieldValue('compare_offset_amount', null);
      const kind = form.getFieldValue('compare_value_kind');
      if (kind !== 'delta' && kind !== 'percent') form.setFieldValue('compare_value_kind', 'delta');
      return;
    }
    if (mode === 'baseline_days') {
      const kind = form.getFieldValue('compare_value_kind');
      if (kind !== 'delta' && kind !== 'percent') form.setFieldValue('compare_value_kind', 'percent');
      const amount = Number(form.getFieldValue('compare_offset_amount'));
      const fromHours = previous === 'offset_hours' || previous === 'offset_1h' || previous === 'offset_24h';
      if (fromHours || !Number.isInteger(amount) || amount < 2 || amount > 7) {
        form.setFieldValue('compare_offset_amount', 7);
      }
      return;
    }
    form.setFieldValue('compare_value_kind', 'percent');
    const amount = Number(form.getFieldValue('compare_offset_amount'));
    if (previous === 'baseline_days' || !Number.isInteger(amount) || amount < 1) {
      form.setFieldValue('compare_offset_amount', 1);
    }
  };

  const offsetSelected = compareMode === 'offset_hours' || compareMode === 'offset_days' || compareMode === 'offset_1h' || compareMode === 'offset_24h';

  const runDryRun = async () => {
    const values = form.getFieldsValue(true);
    const payload = buildPayload({
      ...values,
      name: values.name?.trim() || t('apm.policies.metricPreview', '指标预览'),
    });
    if (!payload) return;
    setDryRunning(true);
    try {
      setDryRun(await dryRunPolicy(policyId ? { ...payload, policy_id: policyId } : payload));
    } finally {
      setDryRunning(false);
    }
  };

  const removePolicy = async () => {
    if (!policyId) return;
    setDeleting(true);
    try {
      await deletePolicy(policyId);
      message.success(t('apm.policies.deleted', '策略已删除'));
      router.push('/apm/events/policies');
    } finally {
      setDeleting(false);
    }
  };

  const copyVariable = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      message.success(t('apm.policies.copied', '已复制 {value}', { value }));
    } catch {
      message.error(t('apm.policies.copyFailed', '复制失败，请手动复制'));
    }
  };

  const syncComparator = (comparator: ApmPolicyComparator) => {
    const rows = form.getFieldValue('thresholds') ?? [];
    form.setFieldValue('thresholds', rows.map((row) => ({ ...row, comparator })));
    const recovery = form.getFieldValue('recovery_comparator');
    const higher = comparator === 'gt' || comparator === 'gte';
    const recoveryHigher = recovery === 'gt' || recovery === 'gte';
    if (higher === recoveryHigher) {
      form.setFieldValue('recovery_comparator', higher ? 'lt' : 'gt');
    }
  };

  if (loading)
    return (
      <ApmRouteShell
        title={t(policyId ? 'apm.policies.editEditorTitle' : 'apm.policies.createEditorTitle', policyId ? '编辑告警策略' : '新建告警策略')}
        description={t('apm.policies.editorLoading', '正在加载 APM 策略编辑器')}
        dependency="control"
      >
        <ApmSurface><CatalogState kind="loading" /></ApmSurface>
      </ApmRouteShell>
    );

  const stepItems = [
    {
      title: t('apm.policies.basic', '基本信息'),
      status: 'process' as const,
      description: (
        <div className={styles.stepContent}>
          <Form.Item name="name" label={t('apm.policies.name', '策略名称')} rules={[{ required: true, message: t('apm.policies.nameRequired', '请输入策略名称') }]}>
            <Input maxLength={256} placeholder={t('apm.policies.nameExample', '如：结账错误率')} />
          </Form.Item>
          <Form.Item
            name="alert_name"
            label={t('apm.policies.alertName', '告警名称')}
            tooltip={t('apm.policies.variableCopyHint', '变量可从右侧变量表复制')}
            rules={[{ required: true, message: t('apm.policies.alertNameRequired', '请输入告警名称') }]}
          >
            <Input
              maxLength={512}
              placeholder={`${'${service}'} ${t('apm.common.errorRate', '错误率')} > ${'${threshold}'}`}
            />
          </Form.Item>
          <Form.Item name="evaluation_interval" label={t('apm.policies.evaluationInterval', '检测频率')} rules={[{ required: true, message: t('apm.policies.evaluationIntervalRequired', '请输入检测频率') }]}>
            <NumberWithUnit min={1} max={60} unit={t('apm.policies.minutes', '分钟')} />
          </Form.Item>
        </div>
      ),
    },
    {
      title: t('apm.policies.metricDefinition', '指标定义'),
      status: 'process' as const,
      description: (
        <div className={styles.stepContent}>
          <Form.Item name="service_scope" label={t('apm.common.service', '服务')} rules={[{ required: true, message: t('apm.policies.serviceRequired', '请选择服务') }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={serviceOptions}
              placeholder={t('apm.common.selectService', '选择服务')}
              onChange={(value) => {
                form.setFieldValue('endpoints', []);
                setPreview(null);
                const currentOrganizations = form.getFieldValue('organizations') || [];
                if (currentOrganizations.length) return;
                const selected = decodeServiceScope(value);
                const service = services.find((item) => item.id === selected.serviceId);
                if (service?.organization_ids?.length) {
                  form.setFieldValue('organizations', service.organization_ids);
                }
              }}
            />
          </Form.Item>
          <Form.Item
            name="organizations"
            label={t('apm.policies.organizations', '所属组织')}
            rules={[{ required: true, message: t('apm.common.organizationRequired', '请至少选择一个组织') }]}
          >
            <GroupTreeSelect
              className={styles.organizationControl}
              multiple
              mode="ownership"
              showSearch
              placeholder={t('apm.common.selectOrganization', '选择组织')}
            />
          </Form.Item>
          <Form.Item
            name="handlers"
            label={t('apm.policies.handlers', '处理人')}
          >
            <Select<(string | number)[]>
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              disabled={!organizationKey}
              options={handlerOptions}
              placeholder={organizationKey
                ? t('apm.policies.handlersPlaceholder', '从策略所属组织选择处理人')
                : t('apm.policies.selectOrganizationFirst', '请先选择所属组织')}
            />
          </Form.Item>
          <Form.Item name="endpoints" label={t('apm.common.endpoint', '端点')} extra={t('apm.policies.endpointScopeHint', '不选则按服务级别监控（整体聚合）')}>
            <Select
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              options={endpointOptions}
              placeholder={serviceScope
                ? t('apm.policies.endpointPlaceholder', '选择端点，不选表示全部端点')
                : t('apm.policies.selectServiceFirst', '请先选择服务')}
              disabled={!serviceScope}
            />
          </Form.Item>
          <Form.Item name="metric_type" label={t('apm.policies.metric', '指标')} rules={[{ required: true, message: t('apm.policies.metricRequired', '请选择指标') }]}>
            <MetricTypeSelect onMetricChange={applyMetric} />
          </Form.Item>
          {showSlowThreshold ? (
            <Form.Item
              name="slow_threshold_ms"
              label={t('apm.policies.slowThreshold', '慢阈值 (ms)')}
              rules={[{ required: true, message: t('apm.policies.slowThresholdRequired', '请填写慢阈值') }]}
            >
              <NumberWithUnit min={1} max={600000} unit="ms" aria-label={t('apm.policies.slowThreshold', '慢阈值 (ms)')} />
            </Form.Item>
          ) : null}
          {showApdexThreshold ? (
            <Form.Item
              name="apdex_threshold_ms"
              label={t('apm.policies.apdexThreshold', 'T (ms)')}
              rules={[{ required: true, message: t('apm.policies.apdexThresholdRequired', '请填写 T') }]}
            >
              <NumberWithUnit min={1} max={600000} unit="ms" aria-label={t('apm.policies.apdexThreshold', 'T (ms)')} />
            </Form.Item>
          ) : null}
          <Form.Item name="metric_window" label={t('apm.policies.metricWindow', '汇聚周期')} rules={[{ required: true, message: t('apm.policies.metricWindowRequired', '请输入汇聚周期') }]}>
            <NumberWithUnit min={1} max={1440} unit={t('apm.policies.minutes', '分钟')} />
          </Form.Item>
          {showAggregation ? (
            <Form.Item name="aggregation" label={t('apm.policies.aggregation', '汇聚方法')} rules={[{ required: true, message: t('apm.policies.aggregationRequired', '请选择汇聚方法') }]}>
              <Select
                options={[
                  { value: 'avg', label: 'avg_over_time' },
                  { value: 'last', label: 'last_over_time' },
                  { value: 'max', label: 'max_over_time' },
                  { value: 'min', label: 'min_over_time' },
                ]}
              />
            </Form.Item>
          ) : null}
          <Typography.Text type="secondary" className={styles.scopeHint}>
            {t('apm.policies.scopeHint', '环境已并入服务范围；版本固定为全部版本。')}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: t('apm.policies.condition', '告警条件'),
      status: 'process' as const,
      description: (
        <div className={styles.stepContent}>
          {showCompare ? (
            <>
              <Form.Item name="compare_mode" label={t('apm.policies.compareBaseline', '比较基准')}>
                <CompareBaselineSelect onModeChange={applyCompareMode} />
              </Form.Item>
              {offsetSelected ? (
                <>
                  <Form.Item label={t('apm.policies.compareOffsetMethod', '对照方式')}>
                    <Select
                      aria-label={t('apm.policies.compareOffsetMethod', '对照方式')}
                      value={compareMode === 'offset_days' ? 'offset_days' : 'offset_hours'}
                      onChange={(mode: ApmCompareMode) => {
                        const previous = form.getFieldValue('compare_mode') as ApmCompareMode;
                        form.setFieldValue('compare_mode', mode);
                        applyCompareMode(mode, previous);
                      }}
                      options={[
                        { value: 'offset_hours', label: t('apm.policies.compareOffsetHours', 'N 小时前') },
                        { value: 'offset_days', label: t('apm.policies.compareOffsetDays', 'N 天前') },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item
                    className={styles.offsetAmount}
                    name="compare_offset_amount"
                    label={t(
                      compareMode === 'offset_days' ? 'apm.policies.compareOffsetCountDay' : 'apm.policies.compareOffsetCountHour',
                      compareMode === 'offset_days' ? '天数' : '小时数',
                    )}
                    extra={t('apm.policies.compareOffsetHint', '和这段时间之前、同样长度的窗口比较。')}
                    rules={[{
                      validator: async (_, value) => {
                        const amount = Number(value);
                        const max = compareMode === 'offset_days' ? MAX_COMPARE_OFFSET_DAYS : MAX_COMPARE_OFFSET_HOURS;
                        if (!Number.isInteger(amount) || amount < 1 || amount > max) {
                          throw new Error(t('apm.policies.compareOffsetRequired', '请填写对照的小时数或天数'));
                        }
                        const windowMinutes = Number(form.getFieldValue('metric_window')) || 1;
                        const offsetMinutes = compareMode === 'offset_days' ? amount * 24 * 60 : amount * 60;
                        if (offsetMinutes < windowMinutes) {
                          throw new Error(t('apm.policies.compareOffsetShorterThanWindow', '对照长度不能短于汇聚周期'));
                        }
                      },
                    }]}
                  >
                    <InputNumber<number>
                      min={1}
                      max={compareMode === 'offset_days' ? MAX_COMPARE_OFFSET_DAYS : MAX_COMPARE_OFFSET_HOURS}
                      precision={0}
                    />
                  </Form.Item>
                </>
              ) : null}
              {compareMode === 'baseline_days' ? (
                <Form.Item
                  className={styles.offsetAmount}
                  name="compare_offset_amount"
                  label={t('apm.policies.compareOffsetCountDay', '天数')}
                  extra={t('apm.policies.baselineDaysHint', '和过去这些天里、同一时段的平均值比较。')}
                  rules={[{
                    validator: async (_, value) => {
                      const amount = Number(value);
                      if (!Number.isInteger(amount) || amount < 2 || amount > 7) {
                        throw new Error(t('apm.policies.baselineDaysRange', '天数须在 2 到 7 之间'));
                      }
                    },
                  }]}
                >
                  <InputNumber<number> min={2} max={7} precision={0} />
                </Form.Item>
              ) : null}
              {compareMode === 'previous_window' || compareMode === 'baseline_days' ? (
                <Form.Item name="compare_value_kind" label={t('apm.policies.compareValueKind', '比较方式')}>
                  <Radio.Group
                    options={[
                      { value: 'delta', label: t('apm.policies.compareKindDelta', '变化量 Δ') },
                      { value: 'percent', label: t('apm.policies.compareKindPercent', '变化率 %') },
                    ]}
                  />
                </Form.Item>
              ) : null}
            </>
          ) : null}
          <div className={styles.thresholdBlock}>
            <Typography.Text strong className={styles.thresholdTitle}>{t('apm.policies.threeLevelThresholds', '3 级别阈值')}</Typography.Text>
            <Table
              className={styles.thresholdTable}
              tableLayout="fixed"
              size="small"
              pagination={false}
              rowKey="value"
              dataSource={severityOptions}
              columns={[
                {
                  title: t('apm.alerts.level', '级别'),
                  dataIndex: 'value',
                  width: 96,
                  render: (severity: ApmPolicySeverity, row) => <Tag color={row.color}>{row.label}</Tag>,
                },
                {
                  title: t('apm.policies.comparator', '比较符'),
                  dataIndex: 'value',
                  width: 132,
                  render: (_, __, index) => (
                    <Form.Item name={['thresholds', index, 'comparator']} noStyle>
                      <Select
                        aria-label={t('apm.policies.comparatorAria', '{severity}比较符', { severity: severityOptions[index].label })}
                        onChange={syncComparator}
                        options={comparatorOptions}
                      />
                    </Form.Item>
                  ),
                },
                {
                  title: t('apm.policies.threshold', '阈值'),
                  dataIndex: 'value',
                  render: (_, __, index) => (
                    <Form.Item name={['thresholds', index, 'value']} noStyle>
                      <NumberWithUnit
                        aria-label={t('apm.policies.thresholdAria', '{severity}阈值', { severity: severityOptions[index].label })}
                        min={thresholdBounds.min}
                        max={thresholdBounds.max}
                        placeholder={t('apm.policies.notEnabled', '不启用')}
                        unit={thresholdUnit}
                      />
                    </Form.Item>
                  ),
                },
              ]}
            />
          </div>
          {showMinRequest ? (
            <Form.Item
              className={styles.minRequestCount}
              name="min_request_count"
              label={t('apm.policies.minRequestCount', '最低请求数')}
              tooltip={t('apm.policies.minRequestCountTooltip', '本窗请求数低于该值时不评，试算记为样本不足')}
            >
              <InputNumber<number>
                min={1}
                max={100000}
                placeholder={t('apm.policies.minRequestUnlimited', '不限')}
                aria-label={t('apm.policies.minRequestCount', '最低请求数')}
              />
            </Form.Item>
          ) : null}
          <div className={styles.conditionRows}>
            <div className={styles.conditionRow}>
              <span className={styles.conditionLabel}><span aria-hidden="true">*</span>{t('apm.policies.triggerCondition', '触发条件：')}</span>
              <span className={styles.conditionSentence}>
                <Form.Item name="trigger_after" noStyle rules={[{ required: true }]}>
                  <InputNumber<number> min={1} max={triggerWindow == null ? 60 : 20} aria-label={t('apm.policies.triggerCountAria', '触发次数')} />
                </Form.Item>
                {showCompare ? (
                  <>
                    {t('apm.policies.triggerTimes', '次')}
                    <Select
                      aria-label={t('apm.policies.triggerModeAria', '触发方式')}
                      virtual={false}
                      value={triggerMode}
                      onChange={(mode: 'consecutive' | 'window') => {
                        setTriggerMode(mode);
                        if (mode === 'consecutive') {
                          form.setFieldValue('trigger_window', null);
                          return;
                        }
                        const count = Number(form.getFieldValue('trigger_after') || 1);
                        form.setFieldValue('trigger_window', Math.min(20, Math.max(count, 3)));
                      }}
                      options={[
                        { value: 'consecutive', label: t('apm.policies.triggerConsecutive', '连续') },
                        { value: 'window', label: t('apm.policies.triggerWithinWindow', '在最近 N 个周期内') },
                      ]}
                    />
                    {triggerMode === 'window' ? (
                      <>
                        {t('apm.policies.triggerWithinPrefix', '在最近')}
                        <Form.Item name="trigger_window" noStyle>
                          <InputNumber<number> min={1} max={20} aria-label={t('apm.policies.triggerWindowAria', '周期数')} />
                        </Form.Item>
                        {t('apm.policies.triggerWithinSuffix', '个周期内')}
                      </>
                    ) : null}
                  </>
                ) : t('apm.policies.triggerSentenceSuffix', '个汇聚周期满足阈值时触发告警。')}
              </span>
            </div>
            <div className={styles.conditionRow}>
              <span className={styles.conditionLabel}>{t('apm.policies.autoRecovery', '自动恢复：')}</span>
              <span className={styles.conditionSentence}>
                {t('apm.policies.consecutive', '连续')}
                <Form.Item name="recover_after" noStyle rules={[{ required: true }]}>
                  <InputNumber<number> min={1} max={60} aria-label={t('apm.policies.recoveryCountAria', '连续恢复次数')} />
                </Form.Item>
                {t('apm.policies.recoverySentenceSuffix', '个周期不满足阈值时自动恢复。')}
                {showCompare ? (
                  <>
                    <span>{t('apm.policies.recoveryThreshold', '恢复阈值')}</span>
                    <Form.Item name="recovery_comparator" noStyle>
                      <Select aria-label={t('apm.policies.recoveryComparatorAria', '恢复阈值比较符')} virtual={false} options={recoveryOptions} />
                    </Form.Item>
                    <Form.Item name="recovery_value" noStyle>
                      <NumberWithUnit
                        aria-label={t('apm.policies.recoveryThreshold', '恢复阈值')}
                        placeholder={t('apm.policies.recoveryThresholdPlaceholder', '不填则与触发线相同')}
                        unit={thresholdUnit}
                      />
                    </Form.Item>
                  </>
                ) : null}
              </span>
            </div>
            <div className={styles.conditionRow}>
              <span className={styles.conditionLabel}>{t('apm.policies.noDataAlert', '无数据告警：')}</span>
              <span className={styles.conditionSentence}>
                {t('apm.policies.consecutive', '连续')}
                <Form.Item
                  name="no_data_after"
                  noStyle
                  rules={[
                    {
                      validator: async (_, value) => {
                        if (!value || form.getFieldValue('no_data_severity')) return;
                        throw new Error(t('apm.policies.noDataSeverityRequired', '请选择无数据告警级别'));
                      },
                    },
                  ]}
                >
                  <InputNumber<number> min={1} max={60} placeholder={t('apm.common.close', '关闭')} aria-label={t('apm.policies.noDataCountAria', '无数据持续次数')} />
                </Form.Item>
                {t('apm.policies.noDataSentenceSuffix', '个周期无数据时')}
                <Form.Item
                  name="no_data_severity"
                  noStyle
                  rules={[
                    {
                      validator: async (_, value) => {
                        if (!value || form.getFieldValue('no_data_after')) return;
                        throw new Error(t('apm.policies.noDataCountRequired', '请填写无数据持续次数'));
                      },
                    },
                  ]}
                >
                  <Select
                    aria-label={t('apm.policies.noDataSeverityAria', '无数据告警级别')}
                    allowClear
                    placeholder={t('apm.policies.noDataDisabled', '不触发告警')}
                    options={severityOptions.map((item) => ({
                      value: item.value,
                      label: t('apm.policies.triggerSeverityAlert', '触发{severity}告警', { severity: item.label }),
                    }))}
                  />
                </Form.Item>
              </span>
            </div>
            {noDataSeverity ? (
              <Form.Item
                name="no_data_alert_name"
                label={t('apm.policies.noDataAlertName', '无数据告警名称')}
                className={styles.noDataAlertName}
                extra={t('apm.policies.noDataAlertNameHint', '告警名称模板，变量可从右侧变量表复制')}
                rules={[{ required: true, message: t('apm.policies.noDataAlertNameRequired', '请输入无数据告警名称') }]}
              >
                <Input maxLength={512} placeholder={defaultNoDataAlertName} />
              </Form.Item>
            ) : null}
          </div>
        </div>
      ),
    },
    {
      title: t('apm.policies.notificationConfig', '通知配置'),
      status: 'process' as const,
      description: (
        <div className={styles.stepContent}>
          <Form.Item label={t('apm.alerts.notification', '通知')} required>
            <Space>
              <Switch
                checked={noticeEnabled}
                onChange={(checked) => {
                  setNoticeEnabled(checked);
                  if (!checked) {
                    form.setFieldValue('notification_targets', []);
                  }
                }}
                aria-label={t('apm.policies.enableNotification', '启用通知')}
              />
              <Typography.Text type="secondary">{t(noticeEnabled ? 'apm.policies.notificationEnabled' : 'apm.policies.notificationDisabled', noticeEnabled ? '已开启' : '未开启')}</Typography.Text>
            </Space>
          </Form.Item>
          {noticeEnabled ? (
            <NotificationTargetFields
              targets={notificationTargets}
              channelById={channelById}
              channelsToAdd={availableChannelsToAdd}
              recipients={recipients}
              channelState={channelState}
              recipientState={recipientState}
              refreshing={directoriesRefreshing}
              onRetry={() => void loadNotificationDirectories()}
              onSearchRecipients={scheduleRecipientSearch}
            />
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title={t(policyId ? 'apm.policies.editEditorTitle' : 'apm.policies.createEditorTitle', policyId ? '编辑告警策略' : '新建告警策略')}
      description={t('apm.policies.editorDescription', '四步完成范围、指标、条件和通知配置；预览直接查询 VictoriaTraces。')}
      dependency="control"
    >
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ flex: '152px' }}
        wrapperCol={{ flex: '1 1 0' }}
        onFinish={(values) => void submit(values)}
      >
        <div className={styles.editor}>
          <div className="mb-3">
            <ApmPageBreadcrumb
              parentHref="/apm/events/policies"
              parentLabel={t('apm.policies.title', '告警策略')}
              parentAriaLabel={t('apm.policies.backAria', '返回告警策略')}
              current={(
                <Typography.Title level={2} className="!mb-0 !truncate !text-base !font-semibold">
                  {policyId
                    ? (policyName || t('apm.policies.editEditorTitle', '编辑告警策略'))
                    : t('apm.policies.createEditorTitle', '新建告警策略')}
                </Typography.Title>
              )}
            />
          </div>
          <div className={styles.editorLayout}>
            <div className={styles.editorMain}>
              <Steps direction="vertical" current={0} items={stepItems} />
              <div className={styles.editorFooter}>
                <Link href="/apm/events/policies"><Button>{t('common.cancel', '取消')}</Button></Link>
                {policyId ? (
                  <Popconfirm
                    title={t('apm.policies.deleteEditorConfirm', '确认删除该策略？')}
                    description={t('apm.policies.deleteEditorDescription', '删除后将停止后续评估，历史告警和事件快照不受影响。')}
                    okText={t('common.delete', '删除')}
                    cancelText={t('common.cancel', '取消')}
                    okButtonProps={{ danger: true, loading: deleting }}
                    onConfirm={() => void removePolicy()}
                  >
                    <Button danger icon={<DeleteOutlined />}>{t('common.delete', '删除')}</Button>
                  </Popconfirm>
                ) : null}
                <Button type="primary" htmlType="submit" loading={saving}>
                  {t(policyId ? 'apm.policies.saveAction' : 'apm.policies.createAction', policyId ? '保存策略' : '创建策略')}
                </Button>
              </div>
            </div>
            <aside className={styles.editorSide}>
              <section className={styles.sideSection}>
                <Typography.Title level={2}>{t('apm.policies.templateVariables', '模板变量')}</Typography.Title>
                <Table
                  size="small"
                  pagination={false}
                  rowKey="name"
                  columns={[
                    {
                      title: t('apm.policies.variable', '变量'),
                      dataIndex: 'name',
                      render: (value: string) => <code className={styles.variableCode}>{value}</code>,
                    },
                    { title: t('apm.policies.variableDescription', '说明'), dataIndex: 'source' },
                    {
                      title: t('apm.common.operation', '操作'),
                      dataIndex: 'name',
                      width: 64,
                      render: (value: string) => (
                        <Button type="link" size="small" aria-label={t('apm.policies.copyAria', '复制 {value}', { value })} onClick={() => void copyVariable(value)}>
                          {t('apm.policies.copy', '复制')}
                        </Button>
                      ),
                    },
                  ]}
                  dataSource={templateVariables}
                />
              </section>
              <section className={styles.sideSection}>
                <div className={styles.previewHeading}>
                  <div>
                    <Typography.Title level={2}>{t('apm.policies.metricPreview', '指标预览')}</Typography.Title>
                    <Typography.Text type="secondary">
                      {metricOptions.find((item) => item.value === metricType)?.label ?? metricType}（{thresholdUnit}） · {t('apm.policies.minuteCount', '{count} 分钟', { count: form.getFieldValue('metric_window') ?? 5 })}
                      {selectedScope.environment ? ` · ${selectedScope.environment}` : ''}
                      {previewing
                        ? ` · ${t('apm.policies.previewUpdating', '正在更新')}`
                        : ` · ${t('apm.policies.previewAutoRefresh', '配置变化后自动刷新')}`}
                    </Typography.Text>
                  </div>
                  <Space>
                    <Button type="link" loading={dryRunning} onClick={() => void runDryRun()}>{t('apm.policies.dryRun', '试算')}</Button>
                    <Button type="link" loading={previewing} onClick={() => void runPreview()}>{t('apm.common.refresh', '刷新')}</Button>
                  </Space>
                </div>
                {preview ? (
                  <>
                    <Space className={styles.previewValue}>
                      <Typography.Text strong>
                        {preview.value === null
                          ? preview.data_state === 'insufficient_samples'
                            ? t('apm.policies.previewInsufficientSamples', '样本不足')
                            : preview.data_state === 'missing_baseline'
                              ? preview.reason === 'baseline_zero'
                                ? t('apm.policies.previewBaselineZero', '对照值为 0，无法计算变化率')
                                : t('apm.policies.previewMissingBaseline', '对照缺失')
                              : t('apm.common.noData', '无数据')
                          : compareKind === 'percent'
                            ? `${preview.value}%`
                            : metricType === 'error_rate' && compareKind === 'delta'
                              ? `${Number(preview.value) * 100} ${t('apm.policies.percentagePointUnit', '个百分点')}`
                              : metricType === 'error_rate'
                                ? formatErrorRate(Number(preview.value), false, t)
                                : preview.value}
                      </Typography.Text>
                      <Typography.Text type="secondary">
                        {preview.data_state === 'no_data'
                          ? t('apm.policies.previewNoSamples', 'VictoriaTraces 当前窗口无样本')
                          : preview.data_state === 'insufficient_samples'
                            ? t('apm.policies.previewInsufficientSamples', '样本不足')
                            : preview.data_state === 'missing_baseline'
                              ? preview.reason === 'baseline_zero'
                                ? t('apm.policies.previewBaselineZero', '对照值为 0，无法计算变化率')
                                : t('apm.policies.previewMissingBaseline', '对照缺失')
                              : formatClockTime(preview.evaluated_at)}
                      </Typography.Text>
                    </Space>
                    <div className={styles.previewChart}>
                      <TimeSeriesComposedChart
                        data={previewRows}
                        xDataKey="timestamp"
                        getXLabel={(item) => formatClockTime(String(item.timestamp), false)}
                        xAxisBoundaryGap={false}
                        series={previewSeries}
                      />
                    </div>
                  </>
                ) : (
                  <div className={styles.previewEmpty}>
                    <Typography.Text type="secondary" role="status">
                      {previewing
                        ? t('apm.policies.previewLoading', '正在查询真实指标趋势…')
                        : previewFailed
                          ? t('apm.policies.previewUnavailable', '自动预览暂不可用，可点击右上角刷新重试。')
                          : t('apm.policies.previewEmpty', '选择服务并至少启用一个告警阈值后，将自动加载真实指标趋势。')}
                    </Typography.Text>
                  </div>
                )}
                {dryRun ? (
                  <div className="mt-4">
                    {dryRun.truncated ? (
                      <Typography.Text type="warning" className="mb-2 block">
                        {t('apm.policies.dryRunTruncated', '共 {count} 个目标，只试算前 20 个，请在端点里缩小范围', { count: dryRun.total_targets })}
                      </Typography.Text>
                    ) : null}
                    <Table
                      size="small"
                      pagination={false}
                      rowKey={(row) => `${row.endpoint}|${row.version}`}
                      dataSource={dryRun.items}
                      columns={[
                        {
                          title: t('apm.policies.dryRunTarget', '目标'),
                          dataIndex: 'endpoint',
                          render: (_value, row) => [row.endpoint, row.version].filter(Boolean).join(' ') || t('apm.alerts.serviceLevel', '服务级'),
                        },
                        {
                          title: t('apm.policies.dryRunVerdict', '结论'),
                          dataIndex: 'verdict',
                          render: (verdict: ApmPolicyDryRunResult['items'][number]['verdict']) => (
                            <Tag color={verdict === 'would_trigger' || verdict === 'would_escalate' ? 'red' : verdict === 'would_recover' ? 'green' : verdict === 'ok' ? 'blue' : 'gold'}>
                              {t(VERDICT_KEY[verdict])}
                            </Tag>
                          ),
                        },
                        { title: t('apm.policies.dryRunCurrent', '当前值'), dataIndex: 'current_value', render: (value) => value ?? '—' },
                        { title: t('apm.policies.dryRunBaseline', '对照值'), dataIndex: 'baseline_value', render: (value) => value ?? '—' },
                        ...(compareMode === 'baseline_days'
                          ? [{
                            title: t('apm.policies.dryRunBaselineDaysUsed', '可用天数'),
                            dataIndex: 'baseline_days_used',
                            render: (value: number | null | undefined) => value ?? '—',
                          }]
                          : []),
                        { title: t('apm.policies.dryRunCompared', '比较值'), dataIndex: 'compared_value', render: (value) => value ?? '—' },
                        { title: t('apm.policies.dryRunRequestCount', '请求数'), dataIndex: 'request_count', render: (value) => value ?? '—' },
                        {
                          title: t('apm.policies.dryRunMatchedThreshold', '命中阈值'),
                          dataIndex: 'matched_threshold',
                          render: (threshold: ApmPolicyDryRunResult['items'][number]['matched_threshold']) => (
                            threshold
                              ? `${threshold.comparator} ${thresholdToEditorValue(metricType, compareKind, threshold.value) ?? threshold.value}`
                              : '—'
                          ),
                        },
                        { title: t('apm.policies.dryRunReason', '说明'), dataIndex: 'reason', render: (value: string) => value || '—' },
                      ]}
                    />
                  </div>
                ) : null}
              </section>
            </aside>
          </div>
        </div>
      </Form>
    </ApmRouteShell>
  );
}
