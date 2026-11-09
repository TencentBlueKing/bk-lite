'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ComponentProps, type ReactNode } from 'react';
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
  Tooltip,
  Typography,
  type FormInstance,
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

interface ConditionCardEditor {
  ref: string;
  role: 'regular' | 'guard';
  metric_type: ApmPolicyMetric | 'request_count';
  compare_mode: ApmCompareMode;
  compare_offset_amount: number | null;
  compare_value_kind: ApmCompareValueKind | '';
  min_request_count: number | null;
  slow_threshold_ms: number | null;
  apdex_threshold_ms: number | null;
  thresholds: ThresholdEditorRow[];
  comparator: ApmPolicyComparator;
  value: number | null;
}

interface PolicyEditorValues extends Omit<
  ApmPolicyInput,
  'service_id' | 'environment' | 'version_mode' | 'versions' | 'thresholds' | 'organizations' | 'conditions' | 'dependencies'
> {
  service_scope: string;
  organizations: number[];
  handlers: Array<string | number>;
  thresholds: ThresholdEditorRow[];
  recovery_comparator: ApmPolicyComparator;
  recovery_value: number | null;
  cards: ConditionCardEditor[];
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
  handlers: [],
  notification_targets: [],
  cards: [{
    ref: 'a',
    role: 'regular',
    metric_type: 'error_rate',
    compare_mode: 'absolute',
    compare_offset_amount: null,
    compare_value_kind: '',
    min_request_count: 20,
    slow_threshold_ms: null,
    apdex_threshold_ms: null,
    thresholds: SEVERITIES.map(({ value }) => ({
      severity: value,
      comparator: 'gt' as const,
      value: value === 'warning' ? 5 : null,
    })),
    comparator: 'gte',
    value: null,
  }],
  slo: null,
  burn_long_window_minutes: null,
  burn_short_window_minutes: null,
};

const CONDITION_REFS = ['a', 'b', 'c', 'd', 'e'] as const;

function blankThresholdRows(comparator: ApmPolicyComparator = 'gt'): ThresholdEditorRow[] {
  return SEVERITIES.map(({ value }) => ({ severity: value, comparator, value: null }));
}

function blankCard(ref: string, role: 'regular' | 'guard' = 'regular'): ConditionCardEditor {
  return {
    ref,
    role,
    metric_type: role === 'guard' ? 'request_count' : 'throughput',
    compare_mode: 'absolute',
    compare_offset_amount: null,
    compare_value_kind: '',
    min_request_count: null,
    slow_threshold_ms: null,
    apdex_threshold_ms: null,
    thresholds: blankThresholdRows(),
    comparator: 'gte',
    value: null,
  };
}

function nextConditionRef(used: string[]) {
  return CONDITION_REFS.find((ref) => !used.includes(ref)) ?? 'e';
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
const SLOW_METRICS: ApmPolicyMetric[] = ['slow_request_count', 'slow_request_rate'];
const MIN_REQUEST_METRICS: ApmPolicyMetric[] = ['error_rate', 'slow_request_rate', 'apdex', ...LATENCY_METRICS];

function scalesStoredRatio(metric: ApmPolicyMetric, kind: ApmCompareValueKind | '') {
  return RATIO_METRICS.includes(metric) && kind !== 'percent' && kind !== 'sigma';
}

function thresholdUnitFor(
  metric: ApmPolicyMetric | 'request_count',
  kind: ApmCompareValueKind | '',
  t: (key: string, fallback: string) => string,
) {
  // request_count 只出现在前置条件里，单位同样是次数。
  if (metric === 'request_count') return t('apm.policies.timesUnit', '次');
  if (kind === 'sigma') return 'σ';
  if (kind === 'percent') return t('apm.common.percentUnit', '%');
  const ratio = RATIO_METRICS.includes(metric);
  if (ratio && kind === 'delta') return t('apm.policies.percentagePointUnit', '个百分点');
  if (ratio) return t('apm.common.percentUnit', '%');
  if (LATENCY_METRICS.includes(metric)) return t('apm.common.millisecondUnit', 'ms');
  if (metric === 'slo_burn_rate') return '×';
  if (COUNT_METRICS.includes(metric)) return t('apm.policies.timesUnit', '次');
  return t('apm.policies.perSecondUnit', 'req/s');
}

interface ThresholdColumn {
  ref: string;
  showRef: boolean;
  label: string;
  unit: string;
  namePath: (severityIndex: number, key: 'comparator' | 'value') => Array<string | number>;
  bounds: { min?: number; max?: number };
  anchor: boolean;
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
  if (mode === 'offset_hours' || mode === 'offset_days' || mode === 'offset_1h' || mode === 'offset_24h') {
    return kind === 'delta' ? 'delta' : 'percent';
  }
  return 'percent';
}

const MAX_COMPARE_OFFSET_HOURS = 840;
const MAX_COMPARE_OFFSET_DAYS = 35;

function editorCompareState(policy: {
  compare_mode?: ApmCompareMode | null;
  compare_offset_amount?: number | null;
}): { compare_mode: ApmCompareMode; compare_offset_amount: number | null } {
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

function isOffsetCompare(mode: ApmCompareMode | undefined) {
  return mode === 'offset_hours' || mode === 'offset_days' || mode === 'offset_1h' || mode === 'offset_24h';
}

function compareOffsetError(
  mode: ApmCompareMode | undefined,
  value: unknown,
  windowMinutes: number,
  t: (key: string, fallback: string) => string,
) {
  if (mode === 'baseline_days') {
    const amount = Number(value);
    if (!Number.isInteger(amount) || amount < 2 || amount > 7) {
      return t('apm.policies.baselineDaysRange', '天数须在 2 到 7 之间');
    }
    return null;
  }
  if (!isOffsetCompare(mode)) return null;
  const amount = Number(value);
  const days = mode === 'offset_days';
  const max = days ? MAX_COMPARE_OFFSET_DAYS : MAX_COMPARE_OFFSET_HOURS;
  if (!Number.isInteger(amount) || amount < 1 || amount > max) {
    return t('apm.policies.compareOffsetRequired', '请填写对照的小时数或天数');
  }
  const offsetMinutes = days ? amount * 24 * 60 : amount * 60;
  if (offsetMinutes < windowMinutes) {
    return t('apm.policies.compareOffsetShorterThanWindow', '对照长度不能短于汇聚周期');
  }
  return null;
}

// 条件卡的字段路径是动态的 ['cards', i, key]，这里按无类型表单实例操作。
function applyListedCompareMode(
  form: FormInstance,
  base: Array<string | number>,
  mode: ApmCompareMode,
  previous?: ApmCompareMode,
) {
  const amountPath = [...base, 'compare_offset_amount'];
  const kindPath = [...base, 'compare_value_kind'];
  if (mode === 'absolute') {
    form.setFieldValue(kindPath, '');
    form.setFieldValue(amountPath, null);
    return;
  }
  if (mode === 'previous_window') {
    form.setFieldValue(amountPath, null);
    const kind = form.getFieldValue(kindPath);
    if (kind !== 'delta' && kind !== 'percent') form.setFieldValue(kindPath, 'delta');
    return;
  }
  if (mode === 'baseline_days') {
    const kind = form.getFieldValue(kindPath);
    if (kind !== 'delta' && kind !== 'percent' && kind !== 'sigma') form.setFieldValue(kindPath, 'percent');
    const amount = Number(form.getFieldValue(amountPath));
    const fromHours = previous === 'offset_hours' || previous === 'offset_1h' || previous === 'offset_24h';
    if (fromHours || !Number.isInteger(amount) || amount < 2 || amount > 7) {
      form.setFieldValue(amountPath, 7);
    }
    return;
  }
  const listedKind = form.getFieldValue(kindPath);
  if (!isOffsetCompare(previous) || (listedKind !== 'delta' && listedKind !== 'percent')) {
    form.setFieldValue(kindPath, 'percent');
  }
  const amount = Number(form.getFieldValue(amountPath));
  if (previous === 'baseline_days' || !Number.isInteger(amount) || amount < 1) {
    form.setFieldValue(amountPath, 1);
  }
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
  const selected: ApmCompareMode = value === 'offset_1h' || value === 'offset_24h'
    ? 'offset_hours'
    : (value || 'absolute');
  return (
    <Select
      id={id}
      value={selected}
      onChange={(next: ApmCompareMode) => {
        const previous = value;
        onChange?.(next);
        onModeChange?.(next, previous);
      }}
      options={[
        { value: 'absolute', label: t('apm.policies.compareModeAbsolute', '当前值') },
        { value: 'previous_window', label: t('apm.policies.compareModePreviousWindow', '相对上一等长窗') },
        { value: 'offset_hours', label: t('apm.policies.compareModeOffsetHoursWindow', 'N 小时前同窗') },
        { value: 'offset_days', label: t('apm.policies.compareModeOffsetDaysWindow', 'N 天前同窗') },
        { value: 'baseline_days', label: t('apm.policies.compareModeBaselineDays', '近 N 天同窗均值') },
      ]}
    />
  );
}

function NumberWithUnit({ unit, className, ...props }: ComponentProps<typeof InputNumber<number>> & { unit: string }) {
  return (
    <Space.Compact className={[styles.numberWithUnit, className].filter(Boolean).join(' ')}>
      <InputNumber<number> {...props} />
      {unit ? <span className={styles.numberUnit}>{unit}</span> : null}
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

function guardValueScales(metric: ApmPolicyMetric | 'request_count') {
  return metric === 'error_rate' || metric === 'slow_request_rate' || metric === 'apdex';
}

function cardFromRegular(item: ApmPolicyRegularCondition): ConditionCardEditor {
  return {
    ref: item.ref,
    role: 'regular',
    metric_type: item.metric_type,
    ...editorCompareState(item),
    compare_value_kind: item.compare_value_kind ?? '',
    min_request_count: item.min_request_count ?? null,
    slow_threshold_ms: item.slow_threshold_ms ?? null,
    apdex_threshold_ms: item.apdex_threshold_ms ?? null,
    thresholds: editorRowsFromThresholds(item.metric_type, item.compare_mode, item.compare_value_kind, item.thresholds),
    comparator: 'gte',
    value: null,
  };
}

function cardFromGuard(item: ApmPolicyGuardCondition): ConditionCardEditor {
  return {
    ref: item.ref,
    role: 'guard',
    metric_type: item.metric_type,
    compare_mode: 'absolute',
    compare_offset_amount: null,
    compare_value_kind: '',
    min_request_count: null,
    slow_threshold_ms: item.slow_threshold_ms ?? null,
    apdex_threshold_ms: item.apdex_threshold_ms ?? null,
    thresholds: blankThresholdRows(),
    comparator: item.comparator,
    value: guardValueScales(item.metric_type) ? Number(item.value) * 100 : Number(item.value),
  };
}

function cardsFromPolicy(policy: ApmPolicy): ConditionCardEditor[] {
  const stored = policy.conditions || [];
  const regulars = stored.filter((item): item is ApmPolicyRegularCondition => item.role === 'regular');
  const guards = stored.filter((item): item is ApmPolicyGuardCondition => item.role === 'guard');
  if (regulars.length <= 1 && guards.length === 0) {
    const only = regulars[0];
    if (only) return [cardFromRegular(only)];
    return [cardFromRegular({
      ref: 'a',
      role: 'regular',
      metric_type: policy.metric_type,
      compare_mode: policy.compare_mode,
      compare_offset_amount: policy.compare_offset_amount,
      compare_value_kind: policy.compare_value_kind,
      min_request_count: policy.min_request_count,
      slow_threshold_ms: policy.slow_threshold_ms,
      apdex_threshold_ms: policy.apdex_threshold_ms,
      thresholds: policy.thresholds,
    })];
  }
  return stored.map((item) => (item.role === 'guard' ? cardFromGuard(item) : cardFromRegular(item)));
}

function projectAnchor(values: PolicyEditorValues): PolicyEditorValues {
  const anchor = (values.cards || []).find((card) => card?.role === 'regular');
  if (!anchor || anchor.metric_type === 'request_count') return values;
  return {
    ...values,
    metric_type: anchor.metric_type,
    compare_mode: anchor.compare_mode,
    compare_offset_amount: anchor.compare_offset_amount,
    compare_value_kind: anchor.compare_value_kind,
    min_request_count: anchor.min_request_count,
    slow_threshold_ms: anchor.slow_threshold_ms,
    apdex_threshold_ms: anchor.apdex_threshold_ms,
    thresholds: anchor.thresholds?.length ? anchor.thresholds : values.thresholds,
  };
}

function regularConditionPayload(
  ref: string,
  metric: ApmPolicyMetric,
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
  const cards = values.cards || [];
  const regulars = cards.filter((card) => card?.role === 'regular');
  const guards = cards.filter((card) => card?.role === 'guard');
  if (values.metric_type === 'no_traffic' || values.metric_type === 'slo_burn_rate') return undefined;
  if (regulars.length <= 1 && guards.length === 0) return undefined;
  return cards.map((card) => {
    if (card.role === 'guard') {
      const metric = card.metric_type;
      return {
        ref: card.ref,
        role: 'guard' as const,
        metric_type: metric,
        comparator: card.comparator || 'gte',
        value: guardValueScales(metric) ? Number(card.value) / 100 : Number(card.value),
        slow_threshold_ms: metric === 'slow_request_count' || metric === 'slow_request_rate'
          ? card.slow_threshold_ms ?? null
          : null,
        apdex_threshold_ms: metric === 'apdex' ? card.apdex_threshold_ms ?? 500 : null,
      };
    }
    const metric = card.metric_type === 'request_count' ? 'throughput' : card.metric_type;
    return regularConditionPayload(
      card.ref,
      metric,
      card.compare_mode,
      card.compare_offset_amount,
      card.compare_value_kind,
      card.min_request_count,
      card.slow_threshold_ms,
      card.apdex_threshold_ms,
      card.thresholds,
    );
  });
}

function toEditorValues(policy: ApmPolicy): PolicyEditorValues {
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
    cards: cardsFromPolicy(policy),
  };
}

function buildMetricPreviewPayload(
  values: PolicyEditorValues,
  loadedPolicy: ApmPolicy | null,
  previewName: string,
): ApmPolicyInput | null {
  values = projectAnchor(values);
  const scope = decodeServiceScope(values.service_scope ?? '');
  const compareKind = resolvedCompareKind(values.metric_type, values.compare_mode, values.compare_value_kind);
  const thresholds = normalizeThresholds(values.metric_type, compareKind, values.thresholds);
  if (values.metric_type === 'slo_burn_rate' && !values.slo) return null;
  if (
    !scope.serviceId
    || !scope.environment
    || !values.metric_type
    || !values.metric_window
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
    ...comparePayloadFields(values),
    ...metricParamFields(values),
    ...judgmentFields(values),
    thresholds,
    trigger_after: values.trigger_after || 1,
    recover_after: values.recover_after || 1,
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

// 条件卡三列：左侧字母徽标、中间内容、右侧移除按钮。所有子行都落在中间列，
// 左右边缘和首行的指标下拉对齐，参考监控多指标条件卡。
function ConditionCard({
  letter,
  showLetter = false,
  metric,
  onRemove,
  children,
}: {
  letter: string;
  showLetter?: boolean;
  metric: ReactNode;
  onRemove?: () => void;
  children: ReactNode;
}) {
  return (
    <div
      className={showLetter
        ? 'grid grid-cols-[2rem_minmax(0,1fr)_2rem] items-center gap-2 rounded-md border border-[var(--color-border-2)] p-2'
        : 'grid grid-cols-[minmax(0,1fr)_2rem] items-center gap-2 rounded-md border border-[var(--color-border-2)] p-2'}
    >
      {showLetter ? <ConditionRefBadge>{letter}</ConditionRefBadge> : null}
      <div className="min-w-0">{metric}</div>
      {onRemove ? <ConditionRemoveButton onClick={onRemove} /> : <span className="h-8 w-8" />}
      <div className={`${showLetter ? 'col-start-2' : 'col-start-1'} flex min-w-0 flex-col gap-2`}>{children}</div>
    </div>
  );
}

// 条件卡内的一行：固定宽度的小标签 + 控件，控件统一撑满剩余宽度。
function ConditionRow({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[5rem_minmax(0,1fr)] items-start gap-2">
      <span className="flex min-h-8 items-center text-xs text-[var(--color-text-3)]">{label}</span>
      <div className="flex min-w-0 flex-col gap-1">
        {children}
        {hint ? <span className="text-xs text-[var(--color-text-3)]">{hint}</span> : null}
      </div>
    </div>
  );
}

function ConditionRemoveButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation();
  const label = t('apm.policies.removeCondition', '移除');
  return (
    <Tooltip title={label}>
      <Button
        aria-label={label}
        className="h-8 w-8 min-w-0 shrink-0 px-0"
        icon={<CloseOutlined />}
        onClick={onClick}
      />
    </Tooltip>
  );
}

function ConditionRefBadge({ children }: { children: string }) {
  return (
    <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] font-mono text-sm font-semibold text-[var(--color-primary)]">
      {children}
    </span>
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
      className="w-full min-w-0"
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

function ExtraCompareFields({
  fieldName,
  letter,
  mode,
  showChrome,
}: {
  fieldName: number;
  letter: string;
  mode: ApmCompareMode;
  showChrome: boolean;
}) {
  const { t } = useTranslation();
  const form: FormInstance = Form.useFormInstance();
  const amount = Form.useWatch(['cards', fieldName, 'compare_offset_amount'], form);
  const base = ['cards', fieldName];
  useLayoutEffect(() => {
    // 挂载后把 errors / warnings 拆成两份，避免后续 setFieldValue 碰到循环引用告警。
    ['compare_mode', 'compare_offset_amount', 'compare_value_kind'].forEach((key) => {
      const path = ['cards', fieldName, key];
      form.setFieldValue(path, form.getFieldValue(path));
    });
  }, [fieldName, form, mode]);
  useLayoutEffect(() => {
    if (mode !== 'baseline_days' || Number(amount) >= 3) return;
    if (form.getFieldValue(['cards', fieldName, 'compare_value_kind']) !== 'sigma') return;
    form.setFieldValue(['cards', fieldName, 'compare_value_kind'], 'percent');
  }, [amount, fieldName, form, mode]);
  const offsetHours = mode === 'offset_hours' || mode === 'offset_1h' || mode === 'offset_24h';
  const offsetDays = mode === 'offset_days';
  const baseline = mode === 'baseline_days';
  const showKind = mode === 'previous_window' || baseline || offsetHours || offsetDays;
  const showSigma = baseline && Number(amount) >= 3;
  const named = (plain: string, keyed: string) => (showChrome
    ? t(keyed, plain, { ref: letter })
    : plain);
  const amountLabel = baseline || offsetDays
    ? named(
      t('apm.policies.compareOffsetCountDay', '天数'),
      'apm.policies.conditionOffsetDays',
    )
    : named(
      t('apm.policies.compareOffsetCountHour', '小时数'),
      'apm.policies.conditionOffsetHours',
    );
  const amountUnit = baseline || offsetDays
    ? t('apm.policies.dayUnit', '天')
    : t('apm.policies.hourUnit', '小时');
  const validateAmount = async (value: unknown) => {
    const issue = compareOffsetError(
      mode,
      value,
      Number(form.getFieldValue('metric_window')) || 1,
      t,
    );
    if (issue) throw new Error(issue);
  };
  const amountHint = baseline
    ? t('apm.policies.baselineDaysHint', '和过去这些天里、同一时段的平均值比较。')
    : t('apm.policies.compareOffsetHint', '和这段时间之前、同样长度的窗口比较。');
  const compareLabel = showChrome
    ? t('apm.policies.conditionCompare', '条件 {ref} 比较基准', { ref: letter })
    : t('apm.policies.compareBaseline', '比较基准');

  return (
    <>
      <ConditionRow label={t('apm.policies.compareBaseline', '比较基准')}>
        <Form.Item
          name={[fieldName, 'compare_mode']}
          label={compareLabel}
          className={`${styles.conditionField} min-w-0`}
        >
          <CompareBaselineSelect
            onModeChange={(next, previous) => applyListedCompareMode(form, base, next, previous)}
          />
        </Form.Item>
      </ConditionRow>
      {offsetHours || offsetDays || baseline ? (
        <ConditionRow label={baseline || offsetDays
          ? t('apm.policies.compareOffsetCountDay', '天数')
          : t('apm.policies.compareOffsetCountHour', '小时数')} hint={amountHint}>
          <Form.Item
            name={[fieldName, 'compare_offset_amount']}
            label={amountLabel}
            className={`${styles.conditionField} min-w-0`}
            rules={[{ validator: async (_, value) => validateAmount(value) }]}
          >
            <NumberWithUnit
              min={baseline ? 2 : 1}
              max={baseline ? 7 : offsetDays ? MAX_COMPARE_OFFSET_DAYS : MAX_COMPARE_OFFSET_HOURS}
              precision={0}
              unit={amountUnit}
              aria-label={amountLabel}
            />
          </Form.Item>
        </ConditionRow>
      ) : null}
      {showKind ? (
        <ConditionRow label={t('apm.policies.compareValueKind', '比较方式')}>
          <Form.Item
            name={[fieldName, 'compare_value_kind']}
            label={showChrome
              ? t('apm.policies.conditionCompareKind', '条件 {ref} 比较方式', { ref: letter })
              : t('apm.policies.compareValueKind', '比较方式')}
            className={`${styles.conditionField} min-w-0`}
          >
            <Radio.Group
              className="flex min-h-8 flex-wrap items-center gap-x-3"
              options={[
                { value: 'delta', label: t('apm.policies.compareKindDelta', '变化量 Δ') },
                { value: 'percent', label: t('apm.policies.compareKindPercent', '变化率 %') },
                ...(showSigma
                  ? [{ value: 'sigma' as const, label: t('apm.policies.compareKindSigma', '标准差 σ') }]
                  : []),
              ]}
            />
          </Form.Item>
        </ConditionRow>
      ) : null}
    </>
  );
}

function CardMetricSelect({
  value,
  onChange,
  onPicked,
  options,
  ...rest
}: {
  id?: string;
  value?: string;
  onChange?: (value: string) => void;
  onPicked?: (value: ApmPolicyMetric | 'request_count') => void;
  options: Array<{ value: string; label: string }>;
} & Omit<ComponentProps<typeof Select>, 'options' | 'onChange' | 'value'>) {
  return (
    <Select
      {...rest}
      value={value}
      options={options}
      onChange={(next: ApmPolicyMetric | 'request_count') => {
        onChange?.(next);
        onPicked?.(next);
      }}
    />
  );
}

function ApmMetricConditionEditor({
  onMetricChange,
}: {
  onMetricChange?: (value: ApmPolicyMetric, cardIndex: number) => void;
}) {
  const { t } = useTranslation();
  const form = Form.useFormInstance<PolicyEditorValues>();
  const cards = (Form.useWatch('cards', { form, preserve: true }) ?? []) as ConditionCardEditor[];
  const showChrome = cards.length > 1;
  const regularCount = cards.filter((card) => card?.role === 'regular').length;
  const guardCount = cards.length - regularCount;
  const anchorIndex = cards.findIndex((card) => card?.role === 'regular');
  const regularChoices = METRICS
    .filter((item) => item.value !== 'no_traffic' && item.value !== 'slo_burn_rate')
    .map((item) => ({ value: item.value, label: t(item.i18nKey) }));
  const guardChoices = [
    ...regularChoices,
    { value: 'request_count', label: t('apm.policies.metricRequestCount', '请求数') },
  ];
  const typeLabel = t('apm.policies.conditionType', '类型');
  const slowLabel = t('apm.policies.slowThreshold', '慢阈值 (ms)');
  const apdexLabel = t('apm.policies.apdexThreshold', 'T (ms)');
  const minRequestLabel = t('apm.policies.minRequestCount', '最低请求数');
  const guardComparators = [
    { value: 'gt' as const, label: '>' },
    { value: 'gte' as const, label: '≥' },
    { value: 'lt' as const, label: '<' },
    { value: 'lte' as const, label: '≤' },
  ];

  const applyRole = (index: number, next: 'regular' | 'guard') => {
    const current = (form.getFieldValue('cards') || []) as ConditionCardEditor[];
    const card = current[index];
    if (!card || card.role === next) return;
    const regulars = current.filter((item) => item?.role === 'regular').length;
    if (next === 'guard') {
      if (regulars <= 1) return;
      form.setFieldValue(['cards', index], {
        ...card,
        role: 'guard',
        compare_mode: 'absolute',
        compare_offset_amount: null,
        compare_value_kind: '',
        min_request_count: null,
        thresholds: blankThresholdRows(),
        comparator: 'gte',
        value: null,
      });
      return;
    }
    if (regulars >= 3) return;
    const metric = card.metric_type === 'request_count' ? 'throughput' : card.metric_type;
    form.setFieldValue(['cards', index], {
      ...card,
      role: 'regular',
      metric_type: metric,
      compare_mode: 'absolute',
      compare_offset_amount: null,
      compare_value_kind: '',
      thresholds: blankThresholdRows(metric === 'apdex' ? 'lt' : 'gt'),
      value: null,
    });
  };

  return (
    <div className={`${styles.metricEditor} rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] shadow-sm`}>
      <div className="flex min-h-11 items-center border-b border-[var(--color-border-2)] px-3">
        <span className="text-sm font-medium text-[var(--color-text-1)]">
          {t('apm.policies.metricEditor', '指标条件')}
        </span>
      </div>
      <div className="flex flex-col gap-3 p-3">
        <Form.List name="cards">
          {(fields, { add, remove }) => (
            <>
              {fields.map((field) => {
                const card = cards[field.name];
                const ref = card?.ref || CONDITION_REFS[field.name] || 'a';
                const metric = card?.metric_type ?? 'error_rate';
                const role = card?.role ?? 'regular';
                const isAnchor = field.name === anchorIndex;
                const isGuard = role === 'guard';
                const canRemove = cards.length > 1 && !(role === 'regular' && regularCount <= 1);
                const metricLabel = showChrome
                  ? t('apm.policies.conditionMetric', '条件 {ref} 指标', { ref })
                  : t('apm.policies.metric', '指标');
                const slowAccessible = showChrome
                  ? t('apm.policies.conditionSlowThreshold', '条件 {ref} 慢阈值', { ref })
                  : slowLabel;
                const minRequestAccessible = showChrome
                  ? t('apm.policies.conditionMinRequest', '条件 {ref} 最低请求数', { ref })
                  : minRequestLabel;
                return (
                  <ConditionCard
                    key={field.key}
                    letter={ref}
                    showLetter={showChrome}
                    onRemove={canRemove ? () => remove(field.name) : undefined}
                    metric={(
                      <>
                        <Form.Item name={[field.name, 'ref']} hidden><Input /></Form.Item>
                        <Form.Item name={[field.name, 'role']} hidden><Input /></Form.Item>
                        <Form.Item
                          name={[field.name, 'metric_type']}
                          label={metricLabel}
                          className={`${styles.conditionField} min-w-0`}
                        >
                          {isAnchor && !isGuard ? (
                            <MetricTypeSelect onMetricChange={(next) => onMetricChange?.(next, field.name)} />
                          ) : (
                            <CardMetricSelect
                              options={isGuard ? guardChoices : regularChoices}
                              onPicked={(next) => {
                                if (next !== 'request_count') onMetricChange?.(next, field.name);
                              }}
                            />
                          )}
                        </Form.Item>
                      </>
                    )}
                  >
                    {showChrome ? (
                      <ConditionRow label={typeLabel}>
                        <ConditionRoleSelect
                          letter={ref}
                          value={role}
                          disableGuard={role === 'regular' && regularCount <= 1}
                          disableRegular={role === 'guard' && regularCount >= 3}
                          onChange={(next) => applyRole(field.name, next)}
                        />
                      </ConditionRow>
                    ) : null}
                    {(metric === 'slow_request_count' || metric === 'slow_request_rate') ? (
                      <ConditionRow label={slowLabel}>
                        <Form.Item
                          name={[field.name, 'slow_threshold_ms']}
                          label={slowAccessible}
                          rules={[{ required: true, message: t('apm.policies.slowThresholdRequired', '请填写慢阈值') }]}
                          className={`${styles.conditionField} min-w-0`}
                        >
                          <NumberWithUnit min={1} max={600000} unit="ms" aria-label={slowAccessible} />
                        </Form.Item>
                      </ConditionRow>
                    ) : null}
                    {metric === 'apdex' ? (
                      <ConditionRow label={apdexLabel}>
                        <Form.Item
                          name={[field.name, 'apdex_threshold_ms']}
                          label={apdexLabel}
                          rules={[{ required: true, message: t('apm.policies.apdexThresholdRequired', '请填写 T') }]}
                          className={`${styles.conditionField} min-w-0`}
                        >
                          <NumberWithUnit min={1} max={600000} unit="ms" aria-label={apdexLabel} />
                        </Form.Item>
                      </ConditionRow>
                    ) : null}
                    {isGuard ? (
                      <ConditionRow label={t('apm.policies.guardValue', '门槛')}>
                        <div className="grid grid-cols-[72px_minmax(0,1fr)] items-center gap-1.5">
                          <Form.Item name={[field.name, 'comparator']} className={`${styles.conditionField} min-w-0`}>
                            <Select
                              aria-label={t('apm.policies.conditionComparator', '条件 {ref} 比较符', { ref })}
                              options={guardComparators}
                            />
                          </Form.Item>
                          <Form.Item
                            name={[field.name, 'value']}
                            label={t('apm.policies.conditionGuardValue', '条件 {ref} 门槛', { ref })}
                            rules={[{ required: true, message: t('apm.policies.guardValueRequired', '请填写门槛') }]}
                            className={`${styles.conditionField} min-w-0`}
                          >
                            <InputNumber<number>
                              className="!w-full"
                              controls={false}
                              aria-label={t('apm.policies.conditionGuardValue', '条件 {ref} 门槛', { ref })}
                            />
                          </Form.Item>
                        </div>
                      </ConditionRow>
                    ) : (
                      <>
                        <ExtraCompareFields
                          fieldName={field.name}
                          letter={ref}
                          mode={card?.compare_mode ?? 'absolute'}
                          showChrome={showChrome}
                        />
                        {MIN_REQUEST_METRICS.includes(metric as ApmPolicyMetric) ? (
                          <ConditionRow label={minRequestLabel}>
                            <Form.Item
                              name={[field.name, 'min_request_count']}
                              label={minRequestAccessible}
                              className={`${styles.conditionField} min-w-0`}
                            >
                              <InputNumber<number>
                                className="!w-full"
                                min={1}
                                max={100000}
                                placeholder={t('apm.policies.minRequestUnlimited', '不限')}
                                aria-label={minRequestAccessible}
                              />
                            </Form.Item>
                          </ConditionRow>
                        ) : null}
                      </>
                    )}
                  </ConditionCard>
                );
              })}
              <Button
                type="dashed"
                icon={<PlusOutlined aria-hidden />}
                className="w-fit"
                disabled={regularCount >= 3 && guardCount >= 2}
                onClick={() => {
                  const used = cards.map((item) => item?.ref).filter(Boolean);
                  const ref = nextConditionRef(used);
                  const role = regularCount >= 3 && guardCount < 2 ? 'guard' : 'regular';
                  add(blankCard(ref, role));
                }}
              >
                {t('apm.policies.addCondition', '添加条件')}
              </Button>
            </>
          )}
        </Form.List>
      </div>
    </div>
  );
}

export default function ApmPolicyEditor({ policyId }: { policyId?: string }) {
  const { t } = useTranslation();
  const router = useRouter();
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
  const storedMetricType = Form.useWatch('metric_type', form) ?? 'error_rate';
  const storedCompareMode = Form.useWatch('compare_mode', form) ?? 'absolute';
  const storedCompareOffset = Form.useWatch('compare_offset_amount', form);
  const storedCompareKind = Form.useWatch('compare_value_kind', form) ?? '';
  const storedMinRequest = Form.useWatch('min_request_count', form);
  const cards = (Form.useWatch('cards', { form, preserve: true }) ?? []) as ConditionCardEditor[];
  const anchorCard = cards.find((card) => card?.role === 'regular');
  const metricType = (anchorCard && anchorCard.metric_type !== 'request_count'
    ? anchorCard.metric_type
    : storedMetricType) as ApmPolicyMetric;
  const compareMode = anchorCard?.compare_mode ?? storedCompareMode;
  const compareOffsetAmount = anchorCard?.compare_offset_amount ?? storedCompareOffset;
  const compareKindRaw = anchorCard?.compare_value_kind ?? storedCompareKind;
  const minRequestCount = anchorCard?.min_request_count ?? storedMinRequest;
  const evaluationInterval = Form.useWatch('evaluation_interval', form);
  const metricWindow = Form.useWatch('metric_window', form);
  const sloId = Form.useWatch('slo', form);
  const burnLongWindow = Form.useWatch('burn_long_window_minutes', form);
  const burnShortWindow = Form.useWatch('burn_short_window_minutes', form);
  // preserve: 直接读 store，而不是按已注册字段拼装；否则条件卡在 remove 后、
  // 旧字段卸载前触发的通知会留下一个空洞项，阈值行多出一列空白控件。
  const templateRows = useMemo(() => {
    const refs = cards.length > 1 ? cards.map((item) => item?.ref).filter(Boolean) : [];
    return [
      ...templateVariables,
      ...refs.map((ref) => ({
        name: `\${${ref}_value}`,
        source: t('apm.policies.variableConditionValue', '条件 {ref} 的当前值', { ref }),
      })),
    ];
  }, [cards, t, templateVariables]);
  const storedThresholds = Form.useWatch('thresholds', form);
  const watchedThresholds = anchorCard?.thresholds ?? storedThresholds;
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
    // 字段挂载后立刻用两份独立空数组写入缓存。触发周期是后挂上的，
    // 所以切换模式后也要再写一次。
    ([
      'compare_mode',
      'compare_value_kind',
      'compare_offset_amount',
      'recovery_comparator',
      'thresholds',
      'apdex_threshold_ms',
      'trigger_window',
    ] as const).forEach((name) => form.setFieldValue(name, form.getFieldValue(name)));
  }, [compareMode, form, loading, triggerMode]);

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
        form.setFieldsValue(policy ? toEditorValues(policy) : DEFAULT_VALUES);
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
  const ratioMetric = RATIO_METRICS.includes(metricType);
  const thresholdUnit = thresholdUnitFor(metricType, compareKind, t);
  const thresholdBounds: { min?: number; max?: number } = compareKind === 'sigma'
    ? { min: 0.5, max: 5 }
    : compareKind === 'percent' || compareKind === 'delta'
      ? (ratioMetric && compareKind === 'delta' ? { min: -100, max: 100 } : {})
      : ratioMetric
        ? { min: 0, max: 100 }
        : { min: 0 };
  // 多条件时阈值按「级别 × 条件」排成表格；每列记录自己的单位和字段路径。
  const showConditionLetters = cards.length > 1;
  const thresholdColumns: ThresholdColumn[] = cards.flatMap((card, cardIndex): ThresholdColumn[] => {
    if (!card || card.role !== 'regular' || card.metric_type === 'request_count') return [];
    const metric = card.metric_type;
    const isAnchor = cardIndex === cards.findIndex((item) => item?.role === 'regular');
    const kind = resolvedCompareKind(metric, card.compare_mode, card.compare_value_kind);
    return [{
      ref: card.ref,
      showRef: showConditionLetters,
      label: metricOptions.find((item) => item.value === metric)?.label ?? metric,
      unit: isAnchor ? thresholdUnit : thresholdUnitFor(metric, kind, t),
      namePath: (index, key) => ['cards', cardIndex, 'thresholds', index, key],
      bounds: isAnchor ? thresholdBounds : {},
      anchor: isAnchor,
    }];
  });
  const thresholdGridColumns = `64px repeat(${thresholdColumns.length}, minmax(180px, 1fr))`;
  // 级别名 64px，每列至少 180px，列间距 12px。不够一列时仍撑满控件宽，多出来的列在表内横滚。
  const thresholdTrackMin = 64 + thresholdColumns.length * (180 + 12);
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
    values = projectAnchor(values);
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
      const anchorIndex = (values.cards || []).findIndex((card) => card?.role === 'regular');
      form.setFields([{
        name: anchorIndex >= 0 ? ['cards', anchorIndex, 'thresholds', 2, 'value'] : ['thresholds', 2, 'value'],
        errors: [error],
      }]);
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
      ...comparePayloadFields(values),
      ...metricParamFields(values),
      ...judgmentFields(values),
      thresholds,
      trigger_after: values.trigger_after,
      recover_after: values.recover_after,
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
    const rows = SEVERITIES.map(({ value }) => ({
      severity: value,
      comparator: 'gte' as const,
      value: fast ? (value === 'critical' ? 14.4 : null) : (value === 'warning' ? 6 : null),
    }));
    form.setFieldValue('burn_long_window_minutes', fast ? 60 : 360);
    form.setFieldValue('burn_short_window_minutes', fast ? 5 : 30);
    form.setFieldValue('compare_mode', 'absolute');
    form.setFieldValue('compare_value_kind', '');
    form.setFieldValue('recovery_value', null);
    form.setFieldValue('thresholds', rows);
    form.setFieldValue(['cards', 0, 'thresholds'], rows);
    form.setFieldValue(['cards', 0, 'compare_mode'], 'absolute');
    form.setFieldValue(['cards', 0, 'compare_value_kind'], '');
  };

  const applyMetric = (metric: ApmPolicyMetric, cardIndex = 0) => {
    form.setFieldValue('metric_type', metric);
    if (metric === 'slo_burn_rate' || metric === 'no_traffic') {
      const current = ((form.getFieldValue('cards') || []) as ConditionCardEditor[])[cardIndex] || blankCard('a');
      form.setFieldValue('cards', [{
        ...blankCard(current.ref || 'a', 'regular'),
        metric_type: metric,
        thresholds: current.thresholds?.length ? current.thresholds : blankThresholdRows(),
      }]);
      form.setFieldValue('compare_mode', 'absolute');
      form.setFieldValue('compare_value_kind', '');
      if (metric === 'slo_burn_rate') {
        form.setFieldValue('recovery_value', null);
        form.setFieldValue('scope_mode', 'service');
        form.setFieldValue('endpoint_mode', 'service');
        form.setFieldValue('instance_mode', 'all');
        form.setFieldValue('target_kind', 'entry');
        if (form.getFieldValue('burn_long_window_minutes') == null) {
          applyBurnPreset('fast');
        }
      }
      return;
    }
    const store = form as FormInstance;
    if (metric === 'apdex' && store.getFieldValue(['cards', cardIndex, 'apdex_threshold_ms']) == null) {
      store.setFieldValue(['cards', cardIndex, 'apdex_threshold_ms'], 500);
      form.setFieldValue('apdex_threshold_ms', 500);
    }
    if (metric === 'apdex') {
      const rows = (store.getFieldValue(['cards', cardIndex, 'thresholds']) || []) as ThresholdEditorRow[];
      store.setFieldValue(['cards', cardIndex, 'thresholds'], rows.map((row) => (
        row.comparator === 'gt' || row.comparator === 'gte' ? { ...row, comparator: 'lt' as const } : row
      )));
      const currentCards = (form.getFieldValue('cards') || []) as ConditionCardEditor[];
      const anchorIndex = currentCards.findIndex((card) => card?.role === 'regular');
      if (anchorIndex === cardIndex) {
        const recovery = form.getFieldValue('recovery_comparator') as ApmPolicyComparator | undefined;
        if (recovery === 'lt' || recovery === 'lte') {
          form.setFieldValue('recovery_comparator', recovery === 'lte' ? 'gte' : 'gt');
        }
      }
    }
  };

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
    const current = (form.getFieldValue('cards') || []) as ConditionCardEditor[];
    const index = current.findIndex((card) => card?.role === 'regular');
    const rows = (index >= 0 ? form.getFieldValue(['cards', index, 'thresholds']) : form.getFieldValue('thresholds')) ?? [];
    if (index >= 0) {
      form.setFieldValue(['cards', index, 'thresholds'], rows.map((row: ThresholdEditorRow) => ({ ...row, comparator })));
    }
    form.setFieldValue('thresholds', rows.map((row: ThresholdEditorRow) => ({ ...row, comparator })));
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
            <ApmMetricConditionEditor onMetricChange={applyMetric} />
          ) : (
            <Form.Item name="metric_type" label={t('apm.policies.metric', '指标')} rules={[{ required: true, message: t('apm.policies.metricRequired', '请选择指标') }]}>
              <MetricTypeSelect onMetricChange={applyMetric} />
            </Form.Item>
          )}
        </div>
      ),
    },
    {
      title: t('apm.policies.condition', '告警条件'),
      status: 'process' as const,
      description: (
        <div className={styles.stepContent}>
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
            {/* 和监控的多条件阈值表同一套：行是级别、列是条件，单条件也走这张表。 */}
            <div className={`${styles.thresholdTable} rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-4 shadow-md`}>
              <div style={{ minWidth: `max(100%, ${thresholdTrackMin}px)` }}>
                <div
                  className="grid items-center gap-x-3 pb-2"
                  style={{ gridTemplateColumns: thresholdGridColumns }}
                >
                  <span />
                  {thresholdColumns.map((column) => (
                    <div key={column.ref} className="flex min-w-0 items-center gap-1.5" title={`${column.label} · ${column.unit}`}>
                      {column.showRef ? (
                        <span className="inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] px-1 font-mono text-xs font-semibold text-[var(--color-primary)]">
                          {column.ref}
                        </span>
                      ) : null}
                      <span className="truncate text-xs text-[var(--color-text-2)]">{column.label}</span>
                      <span className="shrink-0 text-xs text-[var(--color-text-3)]">{column.unit}</span>
                    </div>
                  ))}
                </div>
                {severityOptions.map((row, index) => (
                  <div
                    key={row.value}
                    className="grid items-center gap-x-3 border-t border-[var(--color-border-1)] py-2"
                    style={{ gridTemplateColumns: thresholdGridColumns }}
                  >
                    <span className="inline-flex items-center gap-2 text-sm text-[var(--color-text-1)]">
                      <span
                        className="inline-block h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: ALERT_LEVEL_COLORS[row.value] }}
                      />
                      {row.label}
                    </span>
                    {thresholdColumns.map((column) => (
                      <div key={column.ref} className="grid grid-cols-[72px_minmax(0,1fr)] items-center gap-1.5">
                        <Form.Item name={column.namePath(index, 'comparator')} noStyle>
                          <Select
                            className="w-full"
                            aria-label={column.anchor
                              ? t('apm.policies.comparatorAria', '{severity}比较符', { severity: row.label })
                              : t('apm.policies.conditionComparatorAria', '{ref}{severity}比较符', { ref: column.ref, severity: row.label })}
                            onChange={column.anchor ? syncComparator : undefined}
                            options={comparatorOptions}
                          />
                        </Form.Item>
                        <Form.Item name={column.namePath(index, 'value')} noStyle>
                          <InputNumber<number>
                            className="w-full"
                            controls={false}
                            aria-label={column.anchor
                              ? t('apm.policies.thresholdAria', '{severity}阈值', { severity: row.label })
                              : t('apm.policies.conditionThresholdAria', '{ref}{severity}阈值', { ref: column.ref, severity: row.label })}
                            min={column.bounds.min}
                            max={column.bounds.max}
                            placeholder={t('apm.policies.notEnabled', '不启用')}
                          />
                        </Form.Item>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </Form.Item>
          <Form.Item name="evaluation_interval" label={t('apm.policies.evaluationInterval', '检测频率')} rules={[{ required: true, message: t('apm.policies.evaluationIntervalRequired', '请输入检测频率') }]}>
            <NumberWithUnit min={1} max={60} unit={t('apm.policies.minutes', '分钟')} />
          </Form.Item>
          {metricType === 'slo_burn_rate' ? null : (
            <Form.Item
              name="metric_window"
              label={t('apm.policies.metricWindow', '汇聚周期')}
              dependencies={['evaluation_interval']}
              rules={[
                { required: true, message: t('apm.policies.metricWindowRequired', '请输入汇聚周期') },
                {
                  validator: async (_, value) => {
                    const interval = Number(form.getFieldValue('evaluation_interval')) || 1;
                    if (value != null && Number(value) < interval) {
                      throw new Error(t(
                        'apm.policies.windowShorterThanInterval',
                        '汇聚周期不能短于检测频率，否则两次评估之间的数据不会被检查',
                      ));
                    }
                  },
                },
              ]}
            >
              <NumberWithUnit min={1} max={1440} unit={t('apm.policies.minutes', '分钟')} />
            </Form.Item>
          )}
          {metricType !== 'slo_burn_rate' ? (
            <p className={`${styles.scopeHint} text-xs leading-5 text-[var(--color-text-3)]`}>
              {t('apm.policies.evaluationHint', '每 {interval} 分钟评估一次最近 {window} 分钟的数据', {
                interval: evaluationInterval || 1,
                window: metricWindow || 5,
              })}
            </p>
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
        onFinish={() => void submit(form.getFieldsValue(true) as PolicyEditorValues)}
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
