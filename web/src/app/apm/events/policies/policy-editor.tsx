'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ComponentProps } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { CloseOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button,
  Checkbox,
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
  ApmApplication,
  ApmCompareMode,
  ApmCompareValueKind,
  ApmNotificationChannel,
  ApmNotificationRecipient,
  ApmPolicy,
  ApmPolicyAggregation,
  ApmPolicyComparator,
  ApmPolicyCondition,
  ApmPolicyGuardCondition,
  ApmPolicyRegularCondition,
  ApmPolicyDryRunResult,
  ApmPolicyInput,
  ApmPolicyMetric,
  ApmPolicyQueryResult,
  ApmPolicySeriesPoint,
  ApmPolicySeverity,
  ApmService,
  ApmSlo,
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

interface ExtraConditionEditor {
  ref: string;
  metric_type: ApmPolicyMetric;
  aggregation: ApmPolicyAggregation;
  compare_mode: ApmCompareMode;
  compare_offset_amount: number | null;
  compare_value_kind: ApmCompareValueKind | '';
  min_request_count: number | null;
  slow_threshold_ms: number | null;
  apdex_threshold_ms: number | null;
  thresholds: ThresholdEditorRow[];
}

interface GuardEditor {
  ref: string;
  metric_type: ApmPolicyMetric | 'request_count';
  comparator: ApmPolicyComparator;
  value: number | null;
}

interface PolicyEditorValues extends Omit<
  ApmPolicyInput,
  'service_id' | 'environment' | 'version_mode' | 'versions' | 'thresholds' | 'organizations' | 'conditions' | 'dependencies'
> {
  service_scope: string;
  organizations: number[];
  no_data_alert_name: string;
  handlers: Array<string | number>;
  thresholds: ThresholdEditorRow[];
  recovery_comparator: ApmPolicyComparator;
  recovery_value: number | null;
  extra_conditions: ExtraConditionEditor[];
  guards: GuardEditor[];
  scope_environment?: string;
  dependency_keys?: string[];
  slo?: string | null;
  burn_long_window_minutes?: number | null;
  burn_short_window_minutes?: number | null;
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
  scope_mode: 'service',
  endpoint_mode: 'selected',
  instance_mode: 'all',
  target_kind: 'entry',
  dependency_keys: [],
  service_ids: [],
  scope_environment: '',
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
  extra_conditions: [],
  guards: [],
  slo: null,
  burn_long_window_minutes: null,
  burn_short_window_minutes: null,
};

const CONDITION_REFS = ['b', 'c', 'd', 'e'] as const;

function blankThresholdRows(comparator: ApmPolicyComparator = 'gt'): ThresholdEditorRow[] {
  return SEVERITIES.map(({ value }) => ({ severity: value, comparator, value: null }));
}

function blankExtraCondition(ref: string): ExtraConditionEditor {
  return {
    ref,
    metric_type: 'throughput',
    aggregation: 'avg',
    compare_mode: 'absolute',
    compare_offset_amount: null,
    compare_value_kind: '',
    min_request_count: null,
    slow_threshold_ms: null,
    apdex_threshold_ms: null,
    thresholds: blankThresholdRows(),
  };
}

function nextConditionRef(used: string[]) {
  return CONDITION_REFS.find((ref) => !used.includes(ref)) ?? 'b';
}

function blankGuard(ref: string): GuardEditor {
  return {
    ref,
    metric_type: 'request_count',
    comparator: 'gte',
    value: 200,
  };
}

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
  {
    labelKey: 'apm.policies.metricGroupSlo',
    metrics: [{ value: 'slo_burn_rate', i18nKey: 'apm.policies.metricSloBurnRate' }],
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
  guard_not_met: 'apm.policies.verdictGuardNotMet',
  missing_condition_data: 'apm.policies.verdictMissingConditionData',
  service_not_visible: 'apm.policies.verdictServiceNotVisible',
} as const;

const TEMPLATE_VARIABLES = [
  { name: '${service}', i18nKey: 'apm.policies.variableService' },
  { name: '${instance}', i18nKey: 'apm.policies.variableInstance' },
  { name: '${dependency}', i18nKey: 'apm.policies.variableDependency' },
  { name: '${slo_name}', i18nKey: 'apm.policies.variableSloName' },
  { name: '${burn_rate}', i18nKey: 'apm.policies.variableBurnRate' },
  { name: '${budget_remaining}', i18nKey: 'apm.policies.variableBudgetRemaining' },
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

function encodeDependencyKey(item: { channel: string; system: string; statement: string }) {
  return JSON.stringify({ channel: item.channel, system: item.system, statement: item.statement });
}

function decodeDependencyKey(value: string): NonNullable<ApmPolicyInput['dependencies']>[number] {
  return JSON.parse(value) as NonNullable<ApmPolicyInput['dependencies']>[number];
}

function scopePayload(values: PolicyEditorValues): Partial<ApmPolicyInput> {
  const scopeMode = values.scope_mode || 'service';
  const endpointMode = values.endpoint_mode || 'selected';
  const instanceMode = values.instance_mode || 'all';
  const targetKind = values.target_kind || 'entry';
  const legacy = scopeMode === 'service' && instanceMode === 'all' && endpointMode !== 'all' && targetKind !== 'dependency';
  const scope = legacy
    ? {}
    : {
      scope_mode: scopeMode,
      endpoint_mode: endpointMode,
      instance_mode: instanceMode,
      endpoints: endpointMode === 'selected' ? values.endpoints || [] : [],
      ...(scopeMode === 'services' ? { service_ids: values.service_ids || [] } : {}),
      ...(scopeMode === 'application' && values.application ? { application: values.application } : {}),
    };
  if (targetKind !== 'dependency') return scope;
  return {
    ...scope,
    target_kind: 'dependency',
    dependencies: (values.dependency_keys || []).map((item) => decodeDependencyKey(item)),
    endpoint_mode: 'service',
    instance_mode: 'all',
    endpoints: [],
  };
}

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

const AGGREGATION_OPTIONS: Array<{
  value: ApmPolicyAggregation;
  method: string;
  i18nKey: string;
  fallback: string;
}> = [
  { value: 'avg', method: 'AVG_OVER_TIME', i18nKey: 'apm.policies.aggregationAvg', fallback: '平均' },
  { value: 'last', method: 'LAST_OVER_TIME', i18nKey: 'apm.policies.aggregationLast', fallback: '末值' },
  { value: 'max', method: 'MAX_OVER_TIME', i18nKey: 'apm.policies.aggregationMax', fallback: '最大' },
  { value: 'min', method: 'MIN_OVER_TIME', i18nKey: 'apm.policies.aggregationMin', fallback: '最小' },
];

function aggregationDisplayLabel(name: string, method: string) {
  if (!method || name.trim().toUpperCase() === method) return name;
  return `${name}（${method}）`;
}
const SLOW_METRICS: ApmPolicyMetric[] = ['slow_request_count', 'slow_request_rate'];
const MIN_REQUEST_METRICS: ApmPolicyMetric[] = ['error_rate', 'slow_request_rate', 'apdex', ...LATENCY_METRICS];

function scalesStoredRatio(metric: ApmPolicyMetric, kind: ApmCompareValueKind | '') {
  return RATIO_METRICS.includes(metric) && kind !== 'percent' && kind !== 'sigma';
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
  if (mode === 'baseline_days') {
    if (kind === 'percent' || kind === 'sigma') return kind;
    return 'delta';
  }
  if (mode === 'previous_window') return kind === 'percent' ? 'percent' : 'delta';
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

function NumberWithUnit({ unit, className, ...props }: ComponentProps<typeof InputNumber<number>> & { unit: string }) {
  return (
    <Space.Compact className={[styles.numberWithUnit, className].filter(Boolean).join(' ')}>
      <InputNumber<number> {...props} />
      <span className={styles.numberUnit}>{unit}</span>
    </Space.Compact>
  );
}

function AffixedNumber({
  before,
  after,
  className,
  ...props
}: ComponentProps<typeof InputNumber<number>> & { before?: string; after?: string }) {
  return (
    <Space.Compact className={className}>
      {before ? <span className={styles.numberPrefix}>{before}</span> : null}
      <InputNumber<number> {...props} />
      {after ? <span className={styles.numberUnit}>{after}</span> : null}
    </Space.Compact>
  );
}

function editorRowsFromThresholds(
  metric: ApmPolicyMetric,
  mode: ApmCompareMode | undefined,
  kind: ApmCompareValueKind | '' | undefined,
  thresholds: Array<{ severity: ApmPolicySeverity; comparator: ApmPolicyComparator; value: number | string }>,
): ThresholdEditorRow[] {
  const bySeverity = new Map(thresholds.map((item) => [item.severity, item]));
  const commonComparator = thresholds[0]?.comparator ?? 'gt';
  const resolved = resolvedCompareKind(metric, mode, kind);
  return SEVERITIES.map(({ value: severity }) => {
    const threshold = bySeverity.get(severity);
    return {
      severity,
      comparator: threshold?.comparator ?? commonComparator,
      value: threshold ? thresholdToEditorValue(metric, resolved, threshold.value) : null,
    };
  });
}

function splitStoredConditions(policy: ApmPolicy): Pick<PolicyEditorValues, 'extra_conditions' | 'guards'> {
  const stored = policy.conditions || [];
  const regulars = stored.filter((item): item is ApmPolicyRegularCondition => item.role === 'regular');
  const guards = stored.filter((item): item is ApmPolicyGuardCondition => item.role === 'guard');
  if (regulars.length <= 1 && guards.length === 0) return { extra_conditions: [], guards: [] };
  return {
    extra_conditions: regulars.slice(1).map((item) => ({
      ref: item.ref,
      metric_type: item.metric_type,
      aggregation: item.aggregation,
      compare_mode: item.compare_mode ?? 'absolute',
      compare_offset_amount: item.compare_offset_amount ?? null,
      compare_value_kind: item.compare_value_kind ?? '',
      min_request_count: item.min_request_count ?? null,
      slow_threshold_ms: item.slow_threshold_ms ?? null,
      apdex_threshold_ms: item.apdex_threshold_ms ?? null,
      thresholds: editorRowsFromThresholds(item.metric_type, item.compare_mode, item.compare_value_kind, item.thresholds),
    })),
    guards: guards.map((item) => ({
      ref: item.ref,
      metric_type: item.metric_type,
      comparator: item.comparator,
      value: item.metric_type === 'error_rate' || item.metric_type === 'slow_request_rate' || item.metric_type === 'apdex'
        ? Number(item.value) * 100
        : Number(item.value),
    })),
  };
}

function regularConditionPayload(
  ref: string,
  metric: ApmPolicyMetric,
  aggregation: ApmPolicyAggregation,
  compareMode: ApmCompareMode,
  compareOffset: number | null,
  compareKindInput: ApmCompareValueKind | '',
  minRequest: number | null,
  slow: number | null,
  apdex: number | null,
  rows: ThresholdEditorRow[],
): ApmPolicyRegularCondition {
  const kind = resolvedCompareKind(metric, compareMode, compareKindInput);
  const offset = compareMode === 'offset_hours' || compareMode === 'offset_days' || compareMode === 'baseline_days';
  return {
    ref,
    role: 'regular',
    metric_type: metric,
    aggregation: COUNT_METRICS.includes(metric) ? 'avg' : aggregation,
    compare_mode: compareMode,
    compare_offset_amount: offset ? compareOffset : null,
    compare_value_kind: kind,
    min_request_count: MIN_REQUEST_METRICS.includes(metric) ? minRequest ?? null : null,
    slow_threshold_ms: SLOW_METRICS.includes(metric) ? slow ?? null : null,
    apdex_threshold_ms: metric === 'apdex' ? apdex ?? 500 : null,
    thresholds: normalizeThresholds(metric, kind, rows),
  };
}

function buildConditions(values: PolicyEditorValues): ApmPolicyCondition[] | undefined {
  const extras = values.extra_conditions || [];
  const guards = (values.guards || []).filter((item) => item.value !== null && item.value !== undefined);
  if (values.metric_type === 'no_traffic' || (!extras.length && !guards.length)) return undefined;
  const anchor = regularConditionPayload(
    'a',
    values.metric_type,
    values.aggregation,
    values.compare_mode || 'absolute',
    values.compare_offset_amount,
    values.compare_value_kind,
    values.min_request_count,
    values.slow_threshold_ms ?? null,
    values.apdex_threshold_ms ?? null,
    values.thresholds,
  );
  return [
    anchor,
    ...extras.map((item) => regularConditionPayload(
      item.ref,
      item.metric_type,
      item.aggregation,
      item.compare_mode,
      item.compare_offset_amount,
      item.compare_value_kind,
      item.min_request_count,
      item.slow_threshold_ms,
      item.apdex_threshold_ms,
      item.thresholds,
    )),
    ...guards.map((item): ApmPolicyGuardCondition => ({
      ref: item.ref,
      role: 'guard',
      metric_type: item.metric_type,
      comparator: item.comparator,
      value: item.metric_type === 'error_rate' || item.metric_type === 'slow_request_rate' || item.metric_type === 'apdex'
        ? Number(item.value) / 100
        : Number(item.value),
    })),
  ];
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
    scope_mode: policy.scope_mode || 'service',
    service_ids: policy.service_ids || [],
    application: policy.application || undefined,
    scope_environment: policy.environment,
    endpoint_mode: policy.endpoint_mode || (policy.endpoints.length ? 'selected' : 'service'),
    instance_mode: policy.instance_mode || 'all',
    target_kind: policy.target_kind || 'entry',
    slo: policy.slo || null,
    burn_long_window_minutes: policy.burn_long_window_minutes ?? null,
    burn_short_window_minutes: policy.burn_short_window_minutes ?? null,
    dependency_keys: (policy.dependencies || []).map((item) => encodeDependencyKey(item)),
    handlers: policy.handlers || [],
    notification_targets: policy.notification_targets.map((target) => ({
      channel_id: target.channel_id,
      recipients: target.recipient_mode === 'none' ? [] : [...target.recipients],
    })),
    ...splitStoredConditions(policy),
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
  if (values.metric_type === 'slo_burn_rate' && !values.slo) return null;
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
    endpoints: values.metric_type === 'slo_burn_rate' ? [] : values.endpoints || [],
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
    ...scopePayload(values),
    ...(values.metric_type === 'slo_burn_rate'
      ? {
        slo: values.slo,
        burn_long_window_minutes: values.burn_long_window_minutes ?? null,
        burn_short_window_minutes: values.burn_short_window_minutes ?? null,
      }
      : {}),
  };
}

function ConditionRefBadge({ children }: { children: string }) {
  return (
    <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] font-mono text-sm font-semibold text-[var(--color-primary)]">
      {children}
    </span>
  );
}

function AggregationSelect({
  id,
  value,
  onChange,
}: {
  id?: string;
  value?: ApmPolicyAggregation;
  onChange?: (value: ApmPolicyAggregation) => void;
}) {
  const { t } = useTranslation();
  return (
    <Select
      id={id}
      showSearch
      optionFilterProp="label"
      value={value}
      onChange={onChange}
      filterOption={(input, option) => {
        const query = input.trim().toLowerCase();
        if (!query) return true;
        const label = String(option?.label || '').toLowerCase();
        const optionValue = String(option?.value || '').toLowerCase();
        return label.includes(query) || optionValue.includes(query);
      }}
    >
      {AGGREGATION_OPTIONS.map((item) => {
        const name = t(item.i18nKey, item.fallback);
        return (
          <Select.Option
            key={item.value}
            value={item.value}
            label={aggregationDisplayLabel(name, item.method)}
          >
            <span className="flex w-full min-w-0 items-center">
              <span className="shrink-0 text-[var(--color-text-1)]">{name}</span>
              <span className="text-[var(--color-text-3)]">（{item.method}）</span>
            </span>
          </Select.Option>
        );
      })}
    </Select>
  );
}

function ConditionRoleSelect({
  letter,
  value,
  onChange,
  disableRegular = false,
  disableGuard = false,
}: {
  letter: string;
  value: 'regular' | 'guard';
  onChange?: (value: 'regular' | 'guard') => void;
  disableRegular?: boolean;
  disableGuard?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <Select
      id={`condition-role-${letter}`}
      aria-label={t('apm.policies.conditionRole', '条件 {ref} 类型', { ref: letter })}
      value={value}
      onChange={onChange}
      options={[
        { value: 'regular', label: t('apm.policies.roleRegular', '常规'), disabled: disableRegular },
        { value: 'guard', label: t('apm.policies.roleGuard', '前置条件'), disabled: disableGuard },
      ]}
    />
  );
}

function ApmMetricConditionEditor({
  id,
  value,
  onChange,
  onMetricChange,
  comparatorOptions,
}: {
  id?: string;
  value?: ApmPolicyMetric;
  onChange?: (value: ApmPolicyMetric) => void;
  onMetricChange?: (value: ApmPolicyMetric) => void;
  comparatorOptions: Array<{ value: ApmPolicyComparator; label: string }>;
}) {
  const { t } = useTranslation();
  const form = Form.useFormInstance<PolicyEditorValues>();
  const extraConditions = Form.useWatch('extra_conditions', form) ?? [];
  const guardRows = Form.useWatch('guards', form) ?? [];
  const listApi = useRef<{
    addExtra: (value: ExtraConditionEditor) => void;
    removeExtra: (index: number) => void;
    addGuard: (value: GuardEditor) => void;
    removeGuard: (index: number) => void;
      }>({
        addExtra: () => undefined,
        removeExtra: () => undefined,
        addGuard: () => undefined,
        removeGuard: () => undefined,
      });
  const metric = value ?? 'error_rate';
  const showAggregation = !COUNT_METRICS.includes(metric);
  const showSlowThreshold = SLOW_METRICS.includes(metric);
  const showApdexThreshold = metric === 'apdex';
  const metricChoices = METRICS
    .filter((item) => item.value !== 'no_traffic')
    .map((item) => ({ value: item.value, label: t(item.i18nKey) }));
  const compareOptions = [
    { value: 'absolute', label: t('apm.policies.compareAbsolute', '绝对值') },
    { value: 'previous_window', label: t('apm.policies.comparePreviousWindow', '上一等长窗') },
    { value: 'offset_hours', label: t('apm.policies.compareOffsetHours', 'N 小时前') },
    { value: 'baseline_days', label: t('apm.policies.compareBaselineDays', '历史同期') },
  ];

  return (
    <div className={`${styles.metricEditor} rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] shadow-sm`}>
      <div className="flex min-h-11 items-center border-b border-[var(--color-border-2)] px-3">
        <span className="text-sm font-medium text-[var(--color-text-1)]">
          {t('apm.policies.metricEditor', '指标条件')}
        </span>
      </div>
      <div className="flex flex-col gap-3 p-3">
        <div className="flex flex-col gap-2 rounded-md border border-[var(--color-border-2)] p-2">
          <div className="grid grid-cols-[2rem_minmax(0,1fr)_2rem] items-center gap-2">
            <ConditionRefBadge>a</ConditionRefBadge>
            <MetricTypeSelect
              id={id}
              value={value}
              onChange={onChange}
              onMetricChange={onMetricChange}
            />
            <span className="h-8 w-8" />
          </div>
          <div className="ml-10 grid grid-cols-[132px_minmax(0,1fr)_minmax(0,1fr)] items-center gap-2">
            <ConditionRoleSelect letter="a" value="regular" disableGuard />
            {showSlowThreshold ? (
                <Form.Item
                  name="slow_threshold_ms"
                  label={t('apm.policies.slowThreshold', '慢阈值 (ms)')}
                  rules={[{ required: true, message: t('apm.policies.slowThresholdRequired', '请填写慢阈值') }]}
                  className={`${styles.conditionField} min-w-0`}
                >
                  <NumberWithUnit min={1} max={600000} unit="ms" aria-label={t('apm.policies.slowThreshold', '慢阈值 (ms)')} />
                </Form.Item>
            ) : null}
              {showApdexThreshold ? (
                <Form.Item
                  name="apdex_threshold_ms"
                  label={t('apm.policies.apdexThreshold', 'T (ms)')}
                  rules={[{ required: true, message: t('apm.policies.apdexThresholdRequired', '请填写 T') }]}
                  className={`${styles.conditionField} min-w-0`}
                >
                  <NumberWithUnit min={1} max={600000} unit="ms" aria-label={t('apm.policies.apdexThreshold', 'T (ms)')} />
                </Form.Item>
              ) : null}
              {showAggregation ? (
                <Form.Item
                  name="aggregation"
                  label={t('apm.policies.aggregation', '汇聚方法')}
                  rules={[{ required: true, message: t('apm.policies.aggregationRequired', '请选择汇聚方法') }]}
                  className={`${styles.conditionField} min-w-0`}
                >
                  <AggregationSelect />
                </Form.Item>
              ) : null}
          </div>
        </div>
        <Form.List name="extra_conditions">
          {(fields, { add, remove }) => {
            listApi.current.addExtra = add;
            listApi.current.removeExtra = remove;
            return fields.map((field) => {
              const extra = extraConditions[field.name];
              const extraMetric = extra?.metric_type ?? 'throughput';
              const ref = extra?.ref || CONDITION_REFS[field.name];
              return (
              <div
                key={`regular-${field.key}`}
                style={{ order: CONDITION_REFS.indexOf(ref as typeof CONDITION_REFS[number]) + 2 }}
                className="flex flex-col gap-2 rounded-md border border-[var(--color-border-2)] p-2"
              >
                <Form.Item name={[field.name, 'ref']} hidden><Input /></Form.Item>
                <div className="grid grid-cols-[2rem_minmax(0,1fr)_2rem] items-center gap-2">
                  <ConditionRefBadge>{ref}</ConditionRefBadge>
                  <Form.Item
                    name={[field.name, 'metric_type']}
                    label={t('apm.policies.conditionMetric', '条件 {ref} 指标', { ref })}
                    className={`${styles.conditionField} min-w-0`}
                  >
                    <Select options={metricChoices} />
                  </Form.Item>
                  <Button
                    aria-label={t('apm.policies.removeCondition', '移除')}
                    className="h-8 w-8"
                    icon={<CloseOutlined />}
                    onClick={() => remove(field.name)}
                  />
                </div>
                <div className="ml-10 grid grid-cols-[132px_minmax(0,1fr)_minmax(0,1fr)] items-center gap-2">
                  <ConditionRoleSelect
                    letter={ref}
                    value="regular"
                    disableGuard={guardRows.length >= 2}
                    onChange={(next) => {
                      if (next !== 'guard' || guardRows.length >= 2 || !extra) return;
                      listApi.current.removeExtra(field.name);
                      listApi.current.addGuard({
                        ref: extra.ref,
                        metric_type: extra.metric_type,
                        comparator: 'gte',
                        value: 200,
                      });
                    }}
                  />
                  {SLOW_METRICS.includes(extraMetric) ? (
                    <Form.Item
                      name={[field.name, 'slow_threshold_ms']}
                      label={t('apm.policies.slowThreshold', '慢阈值 (ms)')}
                      className={`${styles.conditionField} min-w-0`}
                    >
                      <NumberWithUnit min={1} max={600000} unit="ms" />
                    </Form.Item>
                  ) : null}
                  {extraMetric === 'apdex' ? (
                    <Form.Item
                      name={[field.name, 'apdex_threshold_ms']}
                      label={t('apm.policies.apdexThreshold', 'T (ms)')}
                      className={`${styles.conditionField} min-w-0`}
                    >
                      <NumberWithUnit min={1} max={600000} unit="ms" />
                    </Form.Item>
                  ) : null}
                  {!COUNT_METRICS.includes(extraMetric) ? (
                    <Form.Item
                      name={[field.name, 'aggregation']}
                      label={t('apm.policies.conditionAggregation', '条件 {ref} 汇聚方法', { ref })}
                      className={`${styles.conditionField} min-w-0`}
                    >
                      <AggregationSelect />
                    </Form.Item>
                  ) : null}
                  <Form.Item
                    name={[field.name, 'compare_mode']}
                    label={t('apm.policies.conditionCompare', '条件 {ref} 比较基准', { ref })}
                    className={`${styles.conditionField} min-w-0`}
                  >
                    <Select options={compareOptions} />
                  </Form.Item>
                  {MIN_REQUEST_METRICS.includes(extraMetric) ? (
                    <Form.Item
                      name={[field.name, 'min_request_count']}
                      label={t('apm.policies.minRequestCount', '最低请求数')}
                      className={`${styles.conditionField} min-w-0`}
                    >
                      <InputNumber<number> min={1} max={100000} />
                    </Form.Item>
                  ) : null}
                </div>
              </div>
              );
            });
          }}
        </Form.List>
        <Form.List name="guards">
          {(fields, { add, remove }) => {
            listApi.current.addGuard = add;
            listApi.current.removeGuard = remove;
            return fields.map((field) => {
              const guard = guardRows[field.name];
              const ref = guard?.ref || CONDITION_REFS[field.name];
              return (
              <div
                key={`guard-${field.key}`}
                style={{ order: CONDITION_REFS.indexOf(ref as typeof CONDITION_REFS[number]) + 2 }}
                className="flex flex-col gap-2 rounded-md border border-[var(--color-border-2)] p-2"
              >
                <Form.Item name={[field.name, 'ref']} hidden><Input /></Form.Item>
                <div className="grid grid-cols-[2rem_minmax(0,1fr)_2rem] items-center gap-2">
                  <ConditionRefBadge>{ref}</ConditionRefBadge>
                  <Form.Item
                    name={[field.name, 'metric_type']}
                    label={t('apm.policies.conditionMetric', '条件 {ref} 指标', { ref })}
                    className={`${styles.conditionField} min-w-0`}
                  >
                    <Select
                      options={[
                        ...metricChoices,
                        { value: 'request_count', label: t('apm.policies.metricRequestCount', '请求数') },
                      ]}
                    />
                  </Form.Item>
                  <Button
                    aria-label={t('apm.policies.removeCondition', '移除')}
                    className="h-8 w-8"
                    icon={<CloseOutlined />}
                    onClick={() => remove(field.name)}
                  />
                </div>
                <div className="ml-10 grid grid-cols-[132px_minmax(0,1fr)_minmax(0,1fr)] items-center gap-2">
                  <ConditionRoleSelect
                    letter={ref}
                    value="guard"
                    disableRegular={extraConditions.length >= 2}
                    onChange={(next) => {
                      if (next !== 'regular' || extraConditions.length >= 2 || !guard) return;
                      const metric = guard.metric_type === 'request_count' ? 'throughput' : guard.metric_type;
                      listApi.current.removeGuard(field.name);
                      listApi.current.addExtra({ ...blankExtraCondition(guard.ref), metric_type: metric });
                    }}
                  />
                  <Form.Item
                    name={[field.name, 'comparator']}
                    label={t('apm.policies.conditionComparator', '条件 {ref} 比较符', { ref })}
                    className={`${styles.conditionField} min-w-0`}
                  >
                    <Select options={comparatorOptions} />
                  </Form.Item>
                  <Form.Item
                    name={[field.name, 'value']}
                    label={t('apm.policies.conditionGuardValue', '条件 {ref} 门槛', { ref })}
                    className={`${styles.conditionField} min-w-0`}
                  >
                    <InputNumber<number> aria-label={t('apm.policies.conditionGuardValue', '条件 {ref} 门槛', { ref })} />
                  </Form.Item>
                </div>
              </div>
              );
            });
          }}
        </Form.List>
        <Button
          type="dashed"
          icon={<PlusOutlined aria-hidden />}
          className="order-[100] w-fit"
          disabled={extraConditions.length >= 2 && guardRows.length >= 2}
          onClick={() => {
            const used = [
              ...extraConditions.map((item) => item?.ref),
              ...guardRows.map((item) => item?.ref),
            ].filter(Boolean);
            const ref = nextConditionRef(used);
            if (extraConditions.length < 2) {
              listApi.current.addExtra(blankExtraCondition(ref));
            } else if (guardRows.length < 2) {
              listApi.current.addGuard(blankGuard(ref));
            }
          }}
        >
          {t('apm.policies.addCondition', '添加条件')}
        </Button>
      </div>
    </div>
  );
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
    getApplications,
    getServiceClientRollups,
    getSlos,
    isLoading,
    previewPolicy,
    dryRunPolicy,
    updatePolicy,
  } = useApmApi();
  const [form] = Form.useForm<PolicyEditorValues>();
  const serviceScope = Form.useWatch('service_scope', form);
  const scopeMode = Form.useWatch('scope_mode', form) || 'service';
  const endpointMode = Form.useWatch('endpoint_mode', form) || 'selected';
  const instanceMode = Form.useWatch('instance_mode', form) || 'all';
  const targetKind = Form.useWatch('target_kind', form) || 'entry';
  const metricType = Form.useWatch('metric_type', form) ?? 'error_rate';
  const compareMode = Form.useWatch('compare_mode', form) ?? 'absolute';
  const compareOffsetAmount = Form.useWatch('compare_offset_amount', form);
  const compareKindRaw = Form.useWatch('compare_value_kind', form) ?? '';
  const minRequestCount = Form.useWatch('min_request_count', form);
  const evaluationInterval = Form.useWatch('evaluation_interval', form);
  const metricWindow = Form.useWatch('metric_window', form);
  const aggregation = Form.useWatch('aggregation', form);
  const sloId = Form.useWatch('slo', form);
  const burnLongWindow = Form.useWatch('burn_long_window_minutes', form);
  const burnShortWindow = Form.useWatch('burn_short_window_minutes', form);
  const extraConditions = Form.useWatch('extra_conditions', form) ?? [];
  const guardRows = Form.useWatch('guards', form) ?? [];
  const templateRows = useMemo(() => {
    const refs = [
      ...(extraConditions.length || guardRows.length ? ['a'] : []),
      ...extraConditions.map((item) => item?.ref).filter(Boolean),
      ...guardRows.map((item) => item?.ref).filter(Boolean),
    ];
    return [
      ...templateVariables,
      ...refs.map((ref) => ({
        name: `\${${ref}_value}`,
        source: t('apm.policies.variableConditionValue', '条件 {ref} 的当前值', { ref }),
      })),
    ];
  }, [extraConditions, guardRows, t, templateVariables]);
  const watchedThresholds = Form.useWatch('thresholds', form);
  const triggerWindow = Form.useWatch('trigger_window', form);
  const selectedEndpoints = Form.useWatch('endpoints', form);
  const notificationTargets = Form.useWatch('notification_targets', form) ?? [];
  const organizations = Form.useWatch('organizations', form);
  const selectedHandlers = Form.useWatch('handlers', form);
  const organizationKey = (organizations || []).join(',');
  const policyName = Form.useWatch('name', form);
  const [services, setServices] = useState<ApmService[]>([]);
  const [applications, setApplications] = useState<ApmApplication[]>([]);
  const [slos, setSlos] = useState<ApmSlo[]>([]);
  const [dependencyOptions, setDependencyOptions] = useState<Array<{ value: string; label: string }>>([]);
  const [channels, setChannels] = useState<ApmNotificationChannel[]>([]);
  const [recipients, setRecipients] = useState<ApmNotificationRecipient[]>([]);
  const [channelState, setChannelState] = useState<NotificationDirectoryState>('loading');
  const [recipientState, setRecipientState] = useState<NotificationDirectoryState>('loading');
  const [availableEndpoints, setAvailableEndpoints] = useState<string[]>([]);
  const [loadedPolicy, setLoadedPolicy] = useState<ApmPolicy | null>(null);
  const [preview, setPreview] = useState<ApmPolicyQueryResult | null>(null);
  const [triggerMode, setTriggerMode] = useState<'consecutive' | 'window'>('consecutive');
  const [noDataOpen, setNoDataOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewFailed, setPreviewFailed] = useState(false);
  const [dryRun, setDryRun] = useState<ApmPolicyDryRunResult | null>(null);
  const [replayEnabled, setReplayEnabled] = useState(false);
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

  useLayoutEffect(() => {
    if (loading) return;
    // rc-field-form 的 errors 和 warnings 初始指向同一个空数组。字段第一次
    // onChange 会把这份 meta 存进缓存，下一次 setFieldValue 再深比较时就会
    // 报 “There may be circular references”，开发态遮罩会挡住整页。
    // 字段挂载后立刻用两份独立空数组写入缓存。触发周期和无数据是后挂上的，
    // 所以切换模式或开关后也要再写一次。
    ([
      'compare_mode',
      'compare_value_kind',
      'compare_offset_amount',
      'recovery_comparator',
      'thresholds',
      'apdex_threshold_ms',
      'trigger_window',
      'no_data_severity',
      'no_data_after',
      'no_data_alert_name',
    ] as const).forEach((name) => form.setFieldValue(name, form.getFieldValue(name)));
  }, [compareMode, form, loading, noDataOpen, triggerMode]);

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
        setNoDataOpen(Boolean(policy?.no_data_severity));
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

  useEffect(() => {
    if (scopeMode !== 'application' || !getApplications) return undefined;
    let cancelled = false;
    void getApplications()
      .then((items) => {
        if (!cancelled) setApplications(items);
      })
      .catch(() => {
        if (!cancelled) setApplications([]);
      });
    return () => {
      cancelled = true;
    };
  }, [getApplications, scopeMode]);

  useEffect(() => {
    if (metricType !== 'slo_burn_rate' || !getSlos) return undefined;
    let cancelled = false;
    void getSlos()
      .then((items) => {
        if (!cancelled) setSlos(items);
      })
      .catch(() => {
        if (!cancelled) setSlos([]);
      });
    return () => {
      cancelled = true;
    };
  }, [getSlos, metricType]);

  useEffect(() => {
    if (targetKind !== 'dependency' || !getServiceClientRollups) return undefined;
    const decoded = decodeServiceScope(serviceScope || '');
    if (!decoded.serviceId || !decoded.environment) return undefined;
    let cancelled = false;
    const ended = new Date();
    const started = new Date(ended.getTime() - 5 * 60 * 1000);
    void getServiceClientRollups(decoded.serviceId, {
      environment: decoded.environment,
      started_at: started.toISOString(),
      ended_at: ended.toISOString(),
    })
      .then((result) => {
        if (cancelled) return;
        setDependencyOptions((result.rows || []).map((row) => ({
          value: encodeDependencyKey(row),
          label: `${row.system} ${row.statement}`,
        })));
      })
      .catch(() => {
        if (!cancelled) setDependencyOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [getServiceClientRollups, serviceScope, targetKind]);

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
  const showCompare = metricType !== 'no_traffic' && metricType !== 'slo_burn_rate';
  const showMinRequest = MIN_REQUEST_METRICS.includes(metricType);
  const ratioMetric = RATIO_METRICS.includes(metricType);
  const thresholdUnit = compareKind === 'sigma'
    ? 'σ'
    : compareKind === 'percent'
      ? t('apm.common.percentUnit', '%')
      : ratioMetric && compareKind === 'delta'
        ? t('apm.policies.percentagePointUnit', '个百分点')
        : ratioMetric
          ? t('apm.common.percentUnit', '%')
          : LATENCY_METRICS.includes(metricType)
            ? t('apm.common.millisecondUnit', 'ms')
            : metricType === 'slo_burn_rate'
              ? '×'
              : COUNT_METRICS.includes(metricType)
                ? t('apm.policies.timesUnit', '次')
                : t('apm.policies.perSecondUnit', 'req/s');
  const thresholdBounds = compareKind === 'sigma'
    ? { min: 0.5, max: 5 }
    : compareKind === 'percent' || compareKind === 'delta'
      ? (ratioMetric && compareKind === 'delta' ? { min: -100, max: 100 } : {})
      : ratioMetric
        ? { min: 0, max: 100 }
        : { min: 0 };
  const ladderComparator = (watchedThresholds || []).find((row) => row?.comparator)?.comparator || 'gt';
  const recoveryOptions: { value: ApmPolicyComparator; label: string }[] = ladderComparator === 'lt' || ladderComparator === 'lte'
    ? [{ value: 'gt', label: '>' }, { value: 'gte', label: '≥' }]
    : [{ value: 'lt', label: '<' }, { value: 'lte', label: '≤' }];
  const comparatorOptions = metricType === 'slo_burn_rate'
    ? [{ value: 'gt' as const, label: '>' }, { value: 'gte' as const, label: '≥' }]
    : metricType === 'apdex' && compareKind === ''
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
    sloId,
    burnLongWindow,
    burnShortWindow,
  });

  const buildPayload = (values: PolicyEditorValues): ApmPolicyInput | null => {
    const scopeMode = values.scope_mode || 'service';
    const decoded = decodeServiceScope(values.service_scope || '');
    const applicationMatch = applications.find((item) => item.id === values.application);
    const scopedService = scopeMode === 'services'
      ? values.service_ids?.[0] || ''
      : scopeMode === 'application'
        ? services.find((item) => !item.archived_at && item.application_id === applicationMatch?.application_id)?.id || ''
        : decoded.serviceId;
    const scopedEnvironment = scopeMode === 'service' ? decoded.environment : values.scope_environment || '';
    const scope = { serviceId: scopedService, environment: scopedEnvironment };
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
    const conditions = buildConditions(values);
    const payload: ApmPolicyInput = {
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
      ...(conditions ? { conditions } : {}),
      ...scopePayload(values),
    };
    if (values.metric_type === 'slo_burn_rate') {
      const selectedSlo = slos.find((item) => item.id === values.slo);
      if (selectedSlo) {
        payload.service_id = selectedSlo.service_id;
        payload.environment = selectedSlo.environment;
      }
      delete payload.conditions;
      payload.slo = values.slo || null;
      payload.burn_long_window_minutes = values.burn_long_window_minutes ?? null;
      payload.burn_short_window_minutes = values.burn_short_window_minutes ?? null;
      payload.compare_mode = 'absolute';
      payload.compare_offset_amount = null;
      payload.compare_value_kind = '';
      payload.min_request_count = null;
      payload.recovery_threshold = {};
      payload.endpoints = [];
      payload.slow_threshold_ms = null;
      payload.apdex_threshold_ms = null;
    }
    return payload;
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

  const applyBurnPreset = (kind: 'fast' | 'slow') => {
    const fast = kind === 'fast';
    form.setFieldValue('burn_long_window_minutes', fast ? 60 : 360);
    form.setFieldValue('burn_short_window_minutes', fast ? 5 : 30);
    form.setFieldValue('compare_mode', 'absolute');
    form.setFieldValue('compare_value_kind', '');
    form.setFieldValue('recovery_value', null);
    form.setFieldValue('thresholds', SEVERITIES.map(({ value }) => ({
      severity: value,
      comparator: 'gte' as const,
      value: fast ? (value === 'critical' ? 14.4 : null) : (value === 'warning' ? 6 : null),
    })));
  };

  const applyMetric = (metric: ApmPolicyMetric) => {
    if (metric === 'slo_burn_rate') {
      form.setFieldValue('compare_mode', 'absolute');
      form.setFieldValue('compare_value_kind', '');
      form.setFieldValue('recovery_value', null);
      form.setFieldValue('extra_conditions', []);
      form.setFieldValue('guards', []);
      form.setFieldValue('scope_mode', 'service');
      form.setFieldValue('endpoint_mode', 'service');
      form.setFieldValue('instance_mode', 'all');
      form.setFieldValue('target_kind', 'entry');
      if (form.getFieldValue('burn_long_window_minutes') == null) {
        applyBurnPreset('fast');
      }
    }
    if (metric === 'no_traffic') {
      form.setFieldValue('extra_conditions', []);
      form.setFieldValue('guards', []);
    }
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
      if (kind !== 'delta' && kind !== 'percent' && kind !== 'sigma') form.setFieldValue('compare_value_kind', 'percent');
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
      setDryRun(await dryRunPolicy({
        ...payload,
        ...(policyId ? { policy_id: policyId } : {}),
        replay_hours: replayEnabled ? 24 : 0,
      }));
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
          {metricType === 'slo_burn_rate' ? (
            <Form.Item
              name="slo"
              label={t('apm.policies.slo', 'SLO')}
              rules={[{ required: true, message: t('apm.policies.sloRequired', '请选择 SLO') }]}
            >
              <Select
                showSearch
                optionFilterProp="label"
                options={slos.map((item) => ({
                  value: item.id,
                  label: `${item.name} · ${item.service_namespace}/${item.service_name}`,
                }))}
                onChange={(value: string) => {
                  const selected = slos.find((item) => item.id === value);
                  if (!selected) return;
                  form.setFieldValue('service_scope', encodeServiceScope(selected.service_id, selected.environment));
                  form.setFieldValue('scope_mode', 'service');
                  form.setFieldValue('scope_environment', selected.environment);
                  const currentOrganizations = form.getFieldValue('organizations') || [];
                  if (currentOrganizations.length) return;
                  const service = services.find((item) => item.id === selected.service_id);
                  if (service?.organization_ids?.length) {
                    form.setFieldValue('organizations', service.organization_ids);
                  }
                }}
              />
            </Form.Item>
          ) : (
          <>
          <Form.Item name="scope_mode" label={t('apm.policies.scopeMode', '范围模式')}>
            <Select
              options={[
                { value: 'service', label: t('apm.policies.scopeService', '单服务') },
                { value: 'services', label: t('apm.policies.scopeServices', '多服务') },
                { value: 'application', label: t('apm.policies.scopeApplication', '按应用') },
              ]}
            />
          </Form.Item>
          {scopeMode === 'services' ? (
            <Form.Item name="service_ids" label={t('apm.policies.serviceIds', '服务列表')} rules={[{ required: true, message: t('apm.policies.serviceRequired', '请选择服务') }]}>
              <Select
                mode="multiple"
                showSearch
                optionFilterProp="label"
                options={services.filter((item) => !item.archived_at).map((item) => ({
                  value: item.id,
                  label: `${item.namespace ? `${item.namespace} / ` : ''}${item.name}`,
                }))}
              />
            </Form.Item>
          ) : null}
          {scopeMode === 'application' ? (
            <Form.Item name="application" label={t('apm.policies.application', '应用')} rules={[{ required: true, message: t('apm.policies.serviceRequired', '请选择服务') }]}>
              <Select
                showSearch
                optionFilterProp="label"
                options={applications.map((item) => ({ value: item.id, label: item.name }))}
              />
            </Form.Item>
          ) : null}
          {scopeMode !== 'service' ? (
            <Form.Item name="scope_environment" label={t('apm.policies.scopeEnvironment', '环境')} rules={[{ required: true, message: t('apm.policies.serviceRequired', '请选择服务') }]}>
              <Select
                showSearch
                options={[...new Set(services.flatMap((item) => (item.environment_views || []).map((view) => view.environment).filter(Boolean)))].map((environment) => ({
                  value: environment,
                  label: environment,
                }))}
              />
            </Form.Item>
          ) : null}
          {scopeMode === 'service' ? (
          <Form.Item name="service_scope" label={t('apm.common.service', '服务')} rules={[{ required: true, message: t('apm.policies.serviceRequired', '请选择服务') }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={serviceOptions}
              placeholder={t('apm.common.selectService', '选择服务')}
              onChange={(value) => {
                if (form.getFieldValue('endpoint_mode') === 'selected') {
                  form.setFieldValue('endpoints', []);
                }
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
          ) : null}
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
          <Form.Item name="target_kind" label={t('apm.policies.targetKind', '目标类型')}>
            <Select
              options={[
                { value: 'entry', label: t('apm.policies.targetKindEntry', '入口') },
                { value: 'dependency', label: t('apm.policies.targetKindDependency', '下游依赖') },
              ]}
              onChange={(value) => {
                if (value === 'dependency') {
                  form.setFieldValue('endpoint_mode', 'service');
                  form.setFieldValue('instance_mode', 'all');
                  form.setFieldValue('endpoints', []);
                }
              }}
            />
          </Form.Item>
          {targetKind === 'dependency' ? (
            <Form.Item
              name="dependency_keys"
              label={t('apm.policies.dependencies', '下游依赖')}
              extra={t('apm.policies.dependencyHint', '不选则监控当前窗全部依赖，最多 40 条')}
            >
              <Select
                mode="multiple"
                allowClear
                showSearch
                optionFilterProp="label"
                options={dependencyOptions}
                placeholder={serviceScope
                  ? t('apm.policies.dependencyPlaceholder', '选择依赖，不选表示全部')
                  : t('apm.policies.selectServiceFirst', '请先选择服务')}
                disabled={!serviceScope}
              />
            </Form.Item>
          ) : null}
          {targetKind === 'entry' ? (
          <>
          <Form.Item name="endpoint_mode" label={t('apm.policies.endpointMode', '端点模式')}>
            <Select
              options={[
                { value: 'service', label: t('apm.policies.endpointModeService', '服务整体') },
                { value: 'selected', label: t('apm.policies.endpointModeSelected', '手选端点') },
                { value: 'all', label: t('apm.policies.endpointModeAll', '全部端点') },
              ]}
            />
          </Form.Item>
          {endpointMode === 'selected' ? (
          <Form.Item name="endpoints" label={t('apm.common.endpoint', '端点')} extra={t('apm.policies.endpointScopeHint', '不选则按服务级别监控（整体聚合）')}>
            <Select
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              options={endpointOptions}
              placeholder={serviceScope
                ? t('apm.policies.endpointPlaceholder', '选择端点，不选则按服务整体聚合')
                : t('apm.policies.selectServiceFirst', '请先选择服务')}
              disabled={!serviceScope}
            />
          </Form.Item>
          ) : null}
          <Form.Item
            name="instance_mode"
            label={t('apm.policies.instanceMode', '实例维度')}
            extra={instanceMode === 'grouped' ? t('apm.policies.instanceModeHint', '按实例判定会一台一条告警，建议只对核心服务开') : undefined}
          >
            <Select
              options={[
                { value: 'all', label: t('apm.policies.instanceModeAll', '不按实例拆') },
                { value: 'grouped', label: t('apm.policies.instanceModeGrouped', '按实例') },
              ]}
            />
          </Form.Item>
          </>
          ) : null}
          </>
          )}
          {metricType !== 'no_traffic' && metricType !== 'slo_burn_rate' ? (
            <Form.Item
              name="metric_type"
              label={t('apm.policies.metric', '指标')}
              rules={[{ required: true, message: t('apm.policies.metricRequired', '请选择指标') }]}
              className={styles.metricEditorItem}
            >
              <ApmMetricConditionEditor onMetricChange={applyMetric} comparatorOptions={comparatorOptions} />
            </Form.Item>
          ) : (
            <Form.Item name="metric_type" label={t('apm.policies.metric', '指标')} rules={[{ required: true, message: t('apm.policies.metricRequired', '请选择指标') }]}>
              <MetricTypeSelect onMetricChange={applyMetric} />
            </Form.Item>
          )}
          {metricType === 'slo_burn_rate' ? null : (
            <Form.Item name="metric_window" label={t('apm.policies.metricWindow', '汇聚周期')} rules={[{ required: true, message: t('apm.policies.metricWindowRequired', '请输入汇聚周期') }]}>
              <NumberWithUnit min={1} max={1440} unit={t('apm.policies.minutes', '分钟')} />
            </Form.Item>
          )}
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
                      ...(compareMode === 'baseline_days'
                        ? [{ value: 'sigma' as const, label: t('apm.policies.compareKindSigma', '标准差 σ') }]
                        : []),
                    ]}
                  />
                </Form.Item>
              ) : null}
            </>
          ) : null}
          {metricType === 'slo_burn_rate' ? (
            <>
              <Form.Item label={t('apm.policies.burnPreset', '燃烧率预设')}>
                <div className="flex gap-2">
                  <Button onClick={() => applyBurnPreset('fast')}>{t('apm.policies.burnFast', '快燃')}</Button>
                  <Button onClick={() => applyBurnPreset('slow')}>{t('apm.policies.burnSlow', '慢燃')}</Button>
                </div>
              </Form.Item>
              <Form.Item
                name="burn_long_window_minutes"
                label={t('apm.policies.burnLongWindow', '长窗（分钟）')}
                rules={[{ required: true, message: t('apm.policies.burnWindowRequired', '请填写燃烧窗口') }]}
              >
                <InputNumber min={60} max={1440} precision={0} className="w-full max-w-[560px]" />
              </Form.Item>
              <Form.Item
                name="burn_short_window_minutes"
                label={t('apm.policies.burnShortWindow', '短窗（分钟）')}
                rules={[{ required: true, message: t('apm.policies.burnWindowRequired', '请填写燃烧窗口') }]}
              >
                <InputNumber min={5} max={720} precision={0} className="w-full max-w-[560px]" />
              </Form.Item>
            </>
          ) : null}
          <Form.Item label={t('apm.policies.alertThreshold', '告警阈值')}>
            <div className="w-full max-w-[560px] rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-4 shadow-md">
              {severityOptions.map((row, index) => (
                <div
                  key={row.value}
                  className="relative mt-[10px] overflow-hidden rounded-md border border-[var(--color-border-2)] p-3 first:mt-0"
                >
                  <div
                    className="absolute bottom-0 left-0 top-0 w-1"
                    style={{ backgroundColor: ALERT_LEVEL_COLORS[row.value] }}
                  />
                  <div className="pl-[10px]">
                    <div className="my-1 font-[800]">{row.label}</div>
                    <div className="flex items-center">
                      <span className="mr-[10px] shrink-0">{t('apm.policies.whenResultIs', '当结果是')}</span>
                      <Form.Item name={['thresholds', index, 'comparator']} noStyle>
                        <Select
                          className={styles.thresholdComparator}
                          aria-label={t('apm.policies.comparatorAria', '{severity}比较符', { severity: row.label })}
                          onChange={syncComparator}
                          options={comparatorOptions}
                        />
                      </Form.Item>
                      <Form.Item name={['thresholds', index, 'value']} noStyle>
                        <NumberWithUnit
                          className={styles.thresholdValue}
                          aria-label={t('apm.policies.thresholdAria', '{severity}阈值', { severity: row.label })}
                          min={thresholdBounds.min}
                          max={thresholdBounds.max}
                          placeholder={t('apm.policies.notEnabled', '不启用')}
                          unit={thresholdUnit}
                        />
                      </Form.Item>
                      {extraConditions.map((extra, extraIndex) => (
                        <div key={extra?.ref || extraIndex} className="ml-2 flex items-center">
                          <span className="mr-2 shrink-0 text-[var(--color-text-2)]">{extra?.ref}</span>
                          <Form.Item name={['extra_conditions', extraIndex, 'thresholds', index, 'comparator']} noStyle>
                            <Select
                              className={styles.thresholdComparator}
                              aria-label={t('apm.policies.conditionComparatorAria', '{ref}{severity}比较符', { ref: extra?.ref, severity: row.label })}
                              options={comparatorOptions}
                            />
                          </Form.Item>
                          <Form.Item name={['extra_conditions', extraIndex, 'thresholds', index, 'value']} noStyle>
                            <NumberWithUnit
                              className={styles.thresholdValue}
                              aria-label={t('apm.policies.conditionThresholdAria', '{ref}{severity}阈值', { ref: extra?.ref, severity: row.label })}
                              placeholder={t('apm.policies.notEnabled', '不启用')}
                              unit=""
                            />
                          </Form.Item>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Form.Item>
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
          <Form.Item label={t('apm.policies.triggerCondition', '触发条件')} required>
            <Form.Item name="trigger_after" noStyle rules={[{ required: true }]}>
              <AffixedNumber
                className={styles.conditionNumber}
                min={1}
                max={triggerWindow == null ? 60 : 20}
                precision={0}
                before={!showCompare || triggerMode !== 'window' ? t('apm.policies.consecutive', '连续') : undefined}
                after={!showCompare || triggerMode !== 'window' ? t('apm.policies.periodUnit', '个周期') : t('apm.policies.triggerTimes', '次')}
                aria-label={t('apm.policies.triggerCountAria', '触发次数')}
              />
            </Form.Item>
          </Form.Item>
          {showCompare ? (
            <Form.Item label={t('apm.policies.triggerModeAria', '触发方式')}>
              <div className={styles.conditionControls}>
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
                  <Form.Item name="trigger_window" noStyle>
                    <AffixedNumber
                      className={styles.conditionWindow}
                      min={1}
                      max={20}
                      precision={0}
                      before={t('apm.policies.triggerWithinPrefix', '在最近')}
                      after={t('apm.policies.triggerWithinSuffix', '个周期内')}
                      aria-label={t('apm.policies.triggerWindowAria', '周期数')}
                    />
                  </Form.Item>
                ) : null}
              </div>
            </Form.Item>
          ) : null}
          <Form.Item label={t('apm.policies.autoRecovery', '自动恢复')}>
            <Form.Item name="recover_after" noStyle rules={[{ required: true }]}>
              <AffixedNumber
                className={styles.conditionNumber}
                min={1}
                max={60}
                precision={0}
                before={t('apm.policies.consecutive', '连续')}
                after={t('apm.policies.periodUnit', '个周期')}
                aria-label={t('apm.policies.recoveryCountAria', '连续恢复次数')}
              />
            </Form.Item>
          </Form.Item>
          {showCompare ? (
            <Form.Item label={t('apm.policies.recoveryThreshold', '恢复阈值')}>
              <Space.Compact className={styles.recoveryCompact}>
                <Form.Item name="recovery_comparator" noStyle>
                  <Select
                    aria-label={t('apm.policies.recoveryComparatorAria', '恢复阈值比较符')}
                    virtual={false}
                    options={recoveryOptions}
                  />
                </Form.Item>
                <Form.Item name="recovery_value" noStyle>
                  <InputNumber<number>
                    className={styles.recoveryValue}
                    aria-label={t('apm.policies.recoveryThreshold', '恢复阈值')}
                    placeholder={t('apm.policies.recoveryThresholdPlaceholder', '不填则与触发线相同')}
                  />
                </Form.Item>
                <span className={styles.numberUnit}>{thresholdUnit}</span>
              </Space.Compact>
            </Form.Item>
          ) : null}
          <Form.Item label={t('apm.policies.noDataAlert', '无数据告警')}>
            <Switch
              checked={noDataOpen}
              aria-label={t('apm.policies.noDataAlert', '无数据告警')}
              onChange={(checked) => {
                setNoDataOpen(checked);
                if (!checked) {
                  form.setFieldValue('no_data_severity', '');
                  form.setFieldValue('no_data_after', null);
                  return;
                }
                if (!form.getFieldValue('no_data_severity')) {
                  form.setFieldValue('no_data_severity', 'warning');
                }
                if (!form.getFieldValue('no_data_after')) {
                  form.setFieldValue('no_data_after', 5);
                }
                if (!form.getFieldValue('no_data_alert_name')) {
                  form.setFieldValue('no_data_alert_name', defaultNoDataAlertName);
                }
              }}
            />
            <div className="mt-[10px] text-xs leading-5 text-[var(--color-text-3)]">
              {t('apm.policies.noDataAlertTip', '连续若干个周期没有数据时触发无数据告警。')}
            </div>
          </Form.Item>
          {noDataOpen ? (
            <>
              <Form.Item
                name="no_data_alert_name"
                label={t('apm.policies.noDataNameLabel', '告警名称')}
                className={styles.noDataAlertName}
                extra={t('apm.policies.noDataAlertNameHint', '告警名称模板，变量可从右侧变量表复制')}
                rules={[{ required: true, message: t('apm.policies.noDataAlertNameRequired', '请输入无数据告警名称') }]}
              >
                <Input maxLength={512} placeholder={defaultNoDataAlertName} />
              </Form.Item>
              <Form.Item
                name="no_data_after"
                label={t('apm.policies.noDataWindow', '持续周期')}
                rules={[{
                  validator: async (_, value) => {
                    if (value) return;
                    throw new Error(t('apm.policies.noDataCountRequired', '请填写无数据持续次数'));
                  },
                }]}
              >
                <AffixedNumber
                  className={styles.conditionNumber}
                  min={1}
                  max={60}
                  precision={0}
                  after={t('apm.policies.periodUnit', '个周期')}
                  aria-label={t('apm.policies.noDataCountAria', '无数据持续次数')}
                />
              </Form.Item>
              <Form.Item
                name="no_data_severity"
                label={t('apm.policies.noDataLevel', '级别')}
                rules={[{
                  validator: async (_, value) => {
                    if (value) return;
                    throw new Error(t('apm.policies.noDataSeverityRequired', '请选择无数据告警级别'));
                  },
                }]}
              >
                <Select
                  className={styles.conditionMode}
                  aria-label={t('apm.policies.noDataSeverityAria', '无数据告警级别')}
                  options={severityOptions.map((item) => ({ value: item.value, label: item.label }))}
                />
              </Form.Item>
            </>
          ) : null}
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
              <section className="min-w-0 overflow-hidden rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-4 shadow-md">
                <div className="mb-3 text-sm font-medium text-[var(--color-text-1)]">
                  {t('apm.policies.templateVariables', '模板变量')}
                </div>
                <Table
                  className={styles.variableTable}
                  size="small"
                  pagination={false}
                  rowKey="name"
                  tableLayout="fixed"
                  columns={[
                    {
                      title: t('apm.policies.variable', '变量'),
                      dataIndex: 'name',
                      width: '44%',
                      ellipsis: true,
                      render: (value: string) => (
                        <span className="font-mono text-xs text-[var(--color-primary)]" title={value}>{value}</span>
                      ),
                    },
                    {
                      title: t('apm.policies.variableDescription', '说明'),
                      dataIndex: 'source',
                      ellipsis: true,
                    },
                    {
                      title: t('apm.common.operation', '操作'),
                      dataIndex: 'name',
                      width: 64,
                      render: (value: string) => (
                        <Button type="link" size="small" className="px-0" aria-label={t('apm.policies.copyAria', '复制 {value}', { value })} onClick={() => void copyVariable(value)}>
                          {t('apm.policies.copy', '复制')}
                        </Button>
                      ),
                    },
                  ]}
                  dataSource={templateRows}
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
                    <Checkbox checked={replayEnabled} onChange={(event) => setReplayEnabled(event.target.checked)}>
                      {t('apm.policies.replay24h', '回放最近 24h')}
                    </Checkbox>
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
                      rowKey={(row) => `${row.service || ''}|${row.instance || ''}|${row.dependency || ''}|${row.endpoint}|${row.version}`}
                      dataSource={dryRun.items}
                      columns={[
                        {
                          title: t('apm.policies.dryRunTarget', '目标'),
                          dataIndex: 'endpoint',
                          render: (_value, row) => [row.service, row.instance, row.dependency, row.endpoint, row.version].filter(Boolean).join(' ') || t('apm.alerts.serviceLevel', '服务级'),
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
                        ...(dryRun.items.some((item) => item.conditions?.length)
                          ? [{
                            title: t('apm.policies.conditions', '条件'),
                            dataIndex: 'conditions',
                            render: (rows: ApmPolicyDryRunResult['items'][number]['conditions']) => (
                              rows || []).map((row) => `${row.ref}: ${row.compared_value ?? '—'}`).join('；'),
                          }]
                          : []),
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
                        ...(dryRun.items.some((item) => item.replay)
                          ? [{
                            title: t('apm.policies.replayHits', '24h 命中'),
                            dataIndex: 'replay',
                            render: (replay: { windows: number; hits: number; hit_at: string[] } | undefined) => (
                              replay ? (
                                <span>
                                  {`${replay.hits}/${replay.windows}`}
                                  {replay.hit_at.length ? <span className="mt-1 block text-xs text-[var(--color-text-3)]">{replay.hit_at.join('、')}</span> : null}
                                </span>
                              ) : '—'
                            ),
                          }]
                          : []),
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
