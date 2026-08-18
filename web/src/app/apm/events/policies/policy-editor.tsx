'use client';

import { useEffect, useMemo, useRef, useState, type ComponentProps } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeftOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  message,
  Popconfirm,
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
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState from '@/app/apm/components/catalog-state';
import TimeSeriesComposedChart from '@/components/time-series-composed-chart';
import { ALERT_LEVEL_COLORS, OBSERVABILITY_SERIES_COLORS } from '@/constants/observabilityChart';
import { useTranslation } from '@/utils/i18n';
import type {
  ApmNotificationChannel,
  ApmPolicy,
  ApmPolicyComparator,
  ApmPolicyInput,
  ApmPolicyMetric,
  ApmPolicyQueryResult,
  ApmPolicySeverity,
  ApmService,
} from '@/app/apm/types';
import styles from '@/app/apm/events/event-workspace.module.scss';

interface ThresholdEditorRow {
  severity: ApmPolicySeverity;
  comparator: ApmPolicyComparator;
  value: number | string | null;
}

interface PolicyEditorValues extends Omit<
  ApmPolicyInput,
  'service_id' | 'environment' | 'version_mode' | 'versions' | 'thresholds' | 'notification_targets'
> {
  service_scope: string;
  no_data_alert_name: string;
  notification_channel_ids: number[];
  notification_recipients: string[];
  thresholds: ThresholdEditorRow[];
}

const SEVERITIES: Array<{ value: ApmPolicySeverity; label: string; color: string }> = [
  { value: 'critical', label: '严重', color: 'red' },
  { value: 'error', label: '错误', color: 'orange' },
  { value: 'warning', label: '警告', color: 'gold' },
];

const DEFAULT_VALUES: PolicyEditorValues = {
  name: '',
  service_scope: '',
  alert_name: '${service} ${metric} ${comparator} ${threshold}',
  endpoints: [],
  metric_type: 'error_rate',
  evaluation_interval: 1,
  metric_window: 5,
  aggregation: 'avg',
  thresholds: SEVERITIES.map(({ value }) => ({
    severity: value,
    comparator: 'gt',
    value: value === 'warning' ? 5 : null,
  })),
  trigger_after: 3,
  recover_after: 3,
  no_data_after: null,
  no_data_severity: '',
  no_data_alert_name: '${service} ${metric} 无数据告警',
  notification_channel_ids: [],
  notification_recipients: [],
};

const METRICS: Array<{ value: ApmPolicyMetric; label: string }> = [
  { value: 'error_rate', label: '错误率' },
  { value: 'p95', label: 'P95 延迟' },
  { value: 'p99', label: 'P99 延迟' },
  { value: 'throughput', label: '吞吐量' },
  { value: 'no_traffic', label: '无流量' },
];

const TEMPLATE_VARIABLES = [
  { name: '${service}', source: '服务名' },
  { name: '${endpoint}', source: '端点' },
  { name: '${version}', source: '版本' },
  { name: '${metric}', source: '指标' },
  { name: '${current_value}', source: '当前值' },
  { name: '${threshold}', source: '阈值' },
  { name: '${level}', source: '告警级别' },
  { name: '${alert_name}', source: '告警名' },
  { name: '${trigger_at}', source: '触发时间' },
  { name: '${group_by}', source: '分组维度' },
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

function thresholdToEditorValue(metric: ApmPolicyMetric, value: number | string) {
  const numeric = Number(value);
  return metric === 'error_rate' && Number.isFinite(numeric) ? numeric * 100 : value;
}

function normalizeThresholds(metric: ApmPolicyMetric, rows: ThresholdEditorRow[] = []) {
  return rows.flatMap((item, index) => {
    if (item.value === null || item.value === '' || item.value === undefined) return [];
    const numericValue = Number(item.value);
    if (!Number.isFinite(numericValue)) return [];
    return [{
      severity: item.severity ?? SEVERITIES[index].value,
      comparator: item.comparator,
      value: metric === 'error_rate' ? numericValue / 100 : numericValue,
    }];
  });
}

function NumberWithUnit({ unit, ...props }: ComponentProps<typeof InputNumber> & { unit: string }) {
  return (
    <Space.Compact className={styles.numberWithUnit}>
      <InputNumber {...props} />
      <span className={styles.numberUnit}>{unit}</span>
    </Space.Compact>
  );
}

function toEditorValues(policy: ApmPolicy): PolicyEditorValues {
  const thresholds = new Map(policy.thresholds.map((item) => [item.severity, item]));
  const commonComparator = policy.thresholds[0]?.comparator ?? 'gt';
  return {
    name: policy.name,
    service_scope: encodeServiceScope(policy.service_id, policy.environment),
    alert_name: policy.alert_name,
    metric_type: policy.metric_type,
    evaluation_interval: policy.evaluation_interval,
    metric_window: policy.metric_window,
    aggregation: policy.aggregation,
    thresholds: SEVERITIES.map(({ value: severity }) => {
      const threshold = thresholds.get(severity);
      return {
        severity,
        comparator: threshold?.comparator ?? commonComparator,
        value: threshold ? thresholdToEditorValue(policy.metric_type, threshold.value) : null,
      };
    }),
    trigger_after: policy.trigger_after,
    recover_after: policy.recover_after,
    no_data_after: policy.no_data_after,
    no_data_severity: policy.no_data_severity,
    no_data_alert_name: policy.no_data_alert_name || '${service} ${metric} 无数据告警',
    endpoints: policy.endpoints,
    notification_channel_ids: policy.notification_targets.map((target) => target.channel_id),
    notification_recipients: Array.from(
      new Set(policy.notification_targets.flatMap((target) => target.recipients)),
    ),
  };
}

function buildMetricPreviewPayload(
  values: PolicyEditorValues,
  loadedPolicy: ApmPolicy | null,
): ApmPolicyInput | null {
  const scope = decodeServiceScope(values.service_scope ?? '');
  const thresholds = normalizeThresholds(values.metric_type, values.thresholds);
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
    name: values.name?.trim() || '指标预览',
    service_id: scope.serviceId,
    environment: scope.environment,
    alert_name: values.alert_name || '',
    endpoints: values.endpoints || [],
    version_mode: preserveLegacyScope ? loadedPolicy?.version_mode ?? 'all' : 'all',
    versions: preserveLegacyScope ? loadedPolicy?.versions ?? [] : [],
    metric_type: values.metric_type,
    evaluation_interval: values.evaluation_interval || 1,
    metric_window: values.metric_window,
    aggregation: values.aggregation,
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
  const {
    createPolicy,
    deletePolicy,
    getNotificationChannels,
    getPolicy,
    getServiceRed,
    getServices,
    isLoading,
    previewPolicy,
    updatePolicy,
  } = useApmApi();
  const [form] = Form.useForm<PolicyEditorValues>();
  const serviceScope = Form.useWatch('service_scope', form);
  const metricType = Form.useWatch('metric_type', form) ?? 'error_rate';
  const evaluationInterval = Form.useWatch('evaluation_interval', form);
  const metricWindow = Form.useWatch('metric_window', form);
  const aggregation = Form.useWatch('aggregation', form);
  const watchedThresholds = Form.useWatch('thresholds', form);
  const selectedEndpoints = Form.useWatch('endpoints', form);
  const noDataSeverity = Form.useWatch('no_data_severity', form);
  const notificationChannelIds = Form.useWatch('notification_channel_ids', form);
  const [services, setServices] = useState<ApmService[]>([]);
  const [channels, setChannels] = useState<ApmNotificationChannel[]>([]);
  const [availableEndpoints, setAvailableEndpoints] = useState<string[]>([]);
  const [loadedPolicy, setLoadedPolicy] = useState<ApmPolicy | null>(null);
  const [preview, setPreview] = useState<ApmPolicyQueryResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewFailed, setPreviewFailed] = useState(false);
  const [noticeEnabled, setNoticeEnabled] = useState(false);
  const previewRequestRef = useRef(0);
  const previewDebounceRef = useRef<number | null>(null);

  useEffect(() => {
    if (isLoading) return;
    setLoading(true);
    Promise.all([
      getServices({ include_archived: true }),
      getNotificationChannels(),
      policyId ? getPolicy(policyId) : Promise.resolve(null),
    ])
      .then(([serviceItems, channelItems, policy]) => {
        setServices(serviceItems);
        setChannels(channelItems);
        setLoadedPolicy(policy);
        setNoticeEnabled(Boolean(policy?.notification_targets.length));
        form.setFieldsValue(policy ? toEditorValues(policy) : DEFAULT_VALUES);
      })
      .finally(() => setLoading(false));
  }, [form, getNotificationChannels, getPolicy, getServices, isLoading, policyId]);

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

  const channelOptions = useMemo(() => {
    const options = channels.map((item) => ({
      value: item.id,
      label: item.availability === 'available'
        ? item.name
        : t('apm.policies.unavailableChannelOption', '{name}（当前不可用）', { name: item.name }),
      disabled: item.availability !== 'available',
    }));
    for (const target of loadedPolicy?.notification_targets || []) {
      if (options.some((item) => item.value === target.channel_id)) continue;
      const name = target.channel_name || t('apm.events.channel', '渠道 {id}', { id: target.channel_id });
      options.push({
        value: target.channel_id,
        label: t('apm.policies.unavailableChannelOption', '{name}（当前不可用）', { name }),
        disabled: true,
      });
    }
    return options;
  }, [channels, loadedPolicy, t]);

  const endpointOptions = useMemo(
    () => Array.from(new Set([...(selectedEndpoints || []), ...availableEndpoints])).map((endpoint) => ({
      value: endpoint,
      label: endpoint,
    })),
    [availableEndpoints, selectedEndpoints],
  );

  const channelRecipientModeMap = useMemo(() => {
    const map = new Map<number, ApmNotificationChannel['recipient_mode'] | undefined>();
    channels.forEach((item) => map.set(item.id, item.recipient_mode));
    (loadedPolicy?.notification_targets || []).forEach((item) => {
      if (!map.has(item.channel_id)) map.set(item.channel_id, item.recipient_mode);
    });
    return map;
  }, [channels, loadedPolicy]);

  const needsNotificationRecipients = (notificationChannelIds || []).some(
    (channelId) => channelRecipientModeMap.get(channelId) !== 'none',
  );

  const selectedScope = decodeServiceScope(serviceScope ?? '');
  const hasLegacyVersionScope = Boolean(loadedPolicy && loadedPolicy.version_mode !== 'all');
  const thresholdUnit = metricType === 'error_rate' ? '%' : metricType === 'p95' || metricType === 'p99' ? 'ms' : '次/秒';
  const previewRows = useMemo(
    () =>
      (preview?.series ?? []).map((point) => ({
        timestamp: point.timestamp,
        value:
          metricType === 'error_rate'
            ? Number(point.error_rate ?? 0) * 100
            : metricType === 'p95'
              ? point.p95_ms
              : metricType === 'p99'
                ? point.p99_ms
                : point.request_rate,
        threshold: preview?.threshold ? thresholdToEditorValue(metricType, preview.threshold.value) : null,
      })),
    [metricType, preview],
  );
  const previewConfiguration = JSON.stringify({
    serviceScope,
    endpoints: selectedEndpoints || [],
    metricType,
    evaluationInterval,
    metricWindow,
    aggregation,
    thresholds: watchedThresholds || [],
  });

  const buildPayload = (values: PolicyEditorValues): ApmPolicyInput | null => {
    const scope = decodeServiceScope(values.service_scope);
    const thresholds = normalizeThresholds(values.metric_type, values.thresholds);
    if (!thresholds.length) {
      form.setFields([{ name: ['thresholds', 2, 'value'], errors: ['至少启用一个告警级别'] }]);
      message.error('至少启用一个告警级别');
      return null;
    }
    if (noticeEnabled && !values.notification_channel_ids?.length) {
      message.error('启用通知后请至少选择一个通知渠道');
      return null;
    }
    if (noticeEnabled && needsNotificationRecipients && !values.notification_recipients?.length) {
      message.error('所选通知渠道需要配置通知对象');
      return null;
    }
    const originalScope = loadedPolicy
      ? encodeServiceScope(loadedPolicy.service_id, loadedPolicy.environment)
      : null;
    const preserveLegacyScope = Boolean(loadedPolicy && values.service_scope === originalScope);
    return {
      name: values.name,
      service_id: scope.serviceId,
      environment: scope.environment,
      alert_name: values.alert_name,
      endpoints: values.endpoints,
      version_mode: preserveLegacyScope ? loadedPolicy?.version_mode ?? 'all' : 'all',
      versions: preserveLegacyScope ? loadedPolicy?.versions ?? [] : [],
      metric_type: values.metric_type,
      evaluation_interval: values.evaluation_interval,
      metric_window: values.metric_window,
      aggregation: values.aggregation,
      thresholds,
      trigger_after: values.trigger_after,
      recover_after: values.recover_after,
      no_data_after: values.no_data_after,
      no_data_severity: values.no_data_severity,
      no_data_alert_name: values.no_data_severity ? values.no_data_alert_name : '',
      notification_targets: noticeEnabled
        ? values.notification_channel_ids.map((channelId) => ({
          channel_id: channelId,
          recipients: channelRecipientModeMap.get(channelId) === 'none'
            ? []
            : values.notification_recipients,
        }))
        : [],
    };
  };

  useEffect(() => {
    if (loading) return;
    const payload = buildMetricPreviewPayload(form.getFieldsValue(true), loadedPolicy);
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
  }, [form, loadedPolicy, loading, previewConfiguration, previewPolicy]);

  const submit = async (values: PolicyEditorValues) => {
    const payload = buildPayload(values);
    if (!payload) return;
    setSaving(true);
    try {
      if (policyId) await updatePolicy(policyId, payload);
      else await createPolicy(payload);
      message.success(
        policyId ? '策略已更新；后续评估使用新配置，历史快照保持不变' : '策略已创建；后续启停只在列表操作',
      );
      router.push('/apm/events/policies');
    } finally {
      setSaving(false);
    }
  };

  const runPreview = async () => {
    const payload = buildMetricPreviewPayload(form.getFieldsValue(true), loadedPolicy);
    if (!payload) {
      message.info('请先选择服务并至少启用一个告警阈值');
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

  const removePolicy = async () => {
    if (!policyId) return;
    setDeleting(true);
    try {
      await deletePolicy(policyId);
      message.success('策略已删除');
      router.push('/apm/events/policies');
    } finally {
      setDeleting(false);
    }
  };

  const copyVariable = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      message.success(`已复制 ${value}`);
    } catch {
      message.error('复制失败，请手动复制');
    }
  };

  const syncComparator = (comparator: ApmPolicyComparator) => {
    const rows = form.getFieldValue('thresholds') ?? [];
    form.setFieldValue('thresholds', rows.map((row) => ({ ...row, comparator })));
  };

  if (loading)
    return (
      <ApmRouteShell
        title={policyId ? '编辑告警策略' : '新建告警策略'}
        description="正在加载 APM 策略编辑器"
        dependency="control"
        spacing="flush"
      >
        <ApmSurface className="m-5"><CatalogState kind="loading" /></ApmSurface>
      </ApmRouteShell>
    );

  const stepItems = [
    {
      title: '基本信息',
      status: 'process' as const,
      description: (
        <div className={styles.stepContent}>
          <Form.Item name="name" label="策略名称" rules={[{ required: true, message: '请输入策略名称' }]}>
            <Input maxLength={256} placeholder="如：结账错误率" />
          </Form.Item>
          <Form.Item
            name="alert_name"
            label="告警名称"
            tooltip="变量可从右侧变量表复制"
            rules={[{ required: true, message: '请输入告警名称' }]}
          >
            <Input maxLength={512} placeholder="${service} 错误率 > ${threshold}" />
          </Form.Item>
          <Form.Item name="evaluation_interval" label="检测频率" rules={[{ required: true, message: '请输入检测频率' }]}>
            <NumberWithUnit min={1} max={60} unit="分钟" />
          </Form.Item>
        </div>
      ),
    },
    {
      title: '指标定义',
      status: 'process' as const,
      description: (
        <div className={styles.stepContent}>
          <Form.Item name="service_scope" label="服务" rules={[{ required: true, message: '请选择服务' }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={serviceOptions}
              placeholder="选择服务"
              onChange={() => {
                form.setFieldValue('endpoints', []);
                setPreview(null);
              }}
            />
          </Form.Item>
          <Form.Item name="endpoints" label="端点" extra="不选则按服务级别监控（整体聚合）">
            <Select
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              options={endpointOptions}
              placeholder={serviceScope ? '选择端点，不选表示全部端点' : '请先选择服务'}
              disabled={!serviceScope}
            />
          </Form.Item>
          <Form.Item name="metric_type" label="指标" rules={[{ required: true, message: '请选择指标' }]}>
            <Select options={METRICS} />
          </Form.Item>
          <Form.Item name="metric_window" label="汇聚周期" rules={[{ required: true, message: '请输入汇聚周期' }]}>
            <NumberWithUnit min={1} max={1440} unit="分钟" />
          </Form.Item>
          <Form.Item name="aggregation" label="汇聚方法" rules={[{ required: true, message: '请选择汇聚方法' }]}>
            <Select
              options={[
                { value: 'avg', label: 'avg_over_time' },
                { value: 'last', label: 'last_over_time' },
                { value: 'max', label: 'max_over_time' },
                { value: 'min', label: 'min_over_time' },
              ]}
            />
          </Form.Item>
          <Typography.Text type="secondary" className={styles.scopeHint}>
            环境已并入服务范围；版本固定为全部版本。
          </Typography.Text>
          {hasLegacyVersionScope ? (
            <Alert
              className={styles.legacyScopeAlert}
              type="info"
              showIcon
              message="当前历史策略含版本范围，保存时继续保留；更换服务后自动切换为全部版本。"
            />
          ) : null}
        </div>
      ),
    },
    {
      title: '告警条件',
      status: 'process' as const,
      description: (
        <div className={styles.stepContent}>
          <Typography.Text strong className={styles.thresholdTitle}>3 级别阈值</Typography.Text>
          <Table
            className={styles.thresholdTable}
            size="small"
            pagination={false}
            rowKey="value"
            dataSource={SEVERITIES}
            columns={[
              {
                title: '级别',
                dataIndex: 'value',
                width: '26%',
                render: (severity: ApmPolicySeverity, row) => <Tag color={row.color}>{row.label}</Tag>,
              },
              {
                title: '比较符',
                dataIndex: 'value',
                width: '32%',
                render: (_, __, index) => (
                  <Form.Item name={['thresholds', index, 'comparator']} noStyle>
                    <Select
                      aria-label={`${SEVERITIES[index].label}比较符`}
                      onChange={syncComparator}
                      options={[
                        { value: 'gt', label: '>' },
                        { value: 'gte', label: '≥' },
                        { value: 'lt', label: '<' },
                        { value: 'lte', label: '≤' },
                      ]}
                    />
                  </Form.Item>
                ),
              },
              {
                title: '阈值',
                dataIndex: 'value',
                render: (_, __, index) => (
                  <Form.Item name={['thresholds', index, 'value']} noStyle>
                    <NumberWithUnit
                      aria-label={`${SEVERITIES[index].label}阈值`}
                      min={0}
                      max={metricType === 'error_rate' ? 100 : undefined}
                      placeholder="不启用"
                      unit={thresholdUnit}
                    />
                  </Form.Item>
                ),
              },
            ]}
          />
          <div className={styles.conditionRows}>
            <div className={styles.conditionRow}>
              <span className={styles.conditionLabel}><span aria-hidden="true">*</span>触发条件：</span>
              <span className={styles.conditionSentence}>
                连续
                <Form.Item name="trigger_after" noStyle rules={[{ required: true }]}>
                  <InputNumber min={1} max={60} aria-label="连续触发次数" />
                </Form.Item>
                个汇聚周期满足阈值时触发告警。
              </span>
            </div>
            <div className={styles.conditionRow}>
              <span className={styles.conditionLabel}>自动恢复：</span>
              <span className={styles.conditionSentence}>
                连续
                <Form.Item name="recover_after" noStyle rules={[{ required: true }]}>
                  <InputNumber min={1} max={60} aria-label="连续恢复次数" />
                </Form.Item>
                个周期不满足阈值时自动恢复。
              </span>
            </div>
            <div className={styles.conditionRow}>
              <span className={styles.conditionLabel}>无数据告警：</span>
              <span className={styles.conditionSentence}>
                连续
                <Form.Item
                  name="no_data_after"
                  noStyle
                  rules={[
                    {
                      validator: async (_, value) => {
                        if (!value || form.getFieldValue('no_data_severity')) return;
                        throw new Error('请选择无数据告警级别');
                      },
                    },
                  ]}
                >
                  <InputNumber min={1} max={60} placeholder="关闭" aria-label="无数据持续次数" />
                </Form.Item>
                个周期无数据时
                <Form.Item
                  name="no_data_severity"
                  noStyle
                  rules={[
                    {
                      validator: async (_, value) => {
                        if (!value || form.getFieldValue('no_data_after')) return;
                        throw new Error('请填写无数据持续次数');
                      },
                    },
                  ]}
                >
                  <Select
                    aria-label="无数据告警级别"
                    allowClear
                    placeholder="不触发告警"
                    options={SEVERITIES.map((item) => ({ value: item.value, label: `触发${item.label}告警` }))}
                  />
                </Form.Item>
              </span>
            </div>
            {noDataSeverity ? (
              <Form.Item
                name="no_data_alert_name"
                label="无数据告警名称"
                className={styles.noDataAlertName}
                extra="告警名称模板，变量可从右侧变量表复制"
                rules={[{ required: true, message: '请输入无数据告警名称' }]}
              >
                <Input maxLength={512} placeholder="${service} ${metric} 无数据告警" />
              </Form.Item>
            ) : null}
          </div>
        </div>
      ),
    },
    {
      title: '通知配置',
      status: 'process' as const,
      description: (
        <div className={styles.stepContent}>
          <Form.Item label="通知" required>
            <Space>
              <Switch
                checked={noticeEnabled}
                onChange={(checked) => {
                  setNoticeEnabled(checked);
                  if (!checked) {
                    form.setFieldValue('notification_channel_ids', []);
                    form.setFieldValue('notification_recipients', []);
                  }
                }}
                aria-label="启用通知"
              />
              <Typography.Text type="secondary">{noticeEnabled ? '已开启' : '未开启'}</Typography.Text>
            </Space>
          </Form.Item>
          {noticeEnabled ? (
            <>
              <Form.Item
                name="notification_channel_ids"
                label="通知通道"
                rules={[
                  { required: true, message: '请选择通知通道' },
                  {
                    validator: async (_, channelIds: number[] | undefined) => {
                      const invalid = channelIds?.some(
                        (channelId) => !channels.some(
                          (item) => item.id === channelId && item.availability === 'available',
                        ),
                      );
                      if (!invalid) return;
                      throw new Error(t('apm.policies.invalidRemove', '已失效，保存前请移除'));
                    },
                  },
                ]}
              >
                <Select
                  mode="multiple"
                  allowClear
                  options={channelOptions}
                  placeholder="选择一个或多个通知通道"
                />
              </Form.Item>
              {needsNotificationRecipients ? (
                <Form.Item
                  name="notification_recipients"
                  label="通知对象"
                  extra="仅需要接收人的通知通道使用此配置"
                  rules={[{ required: true, message: '请输入通知对象' }]}
                >
                  <Select mode="tags" placeholder="输入接收人后回车" />
                </Form.Item>
              ) : null}
            </>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title={policyId ? '编辑告警策略' : '新建告警策略'}
      description="四步完成范围、指标、条件和通知配置；预览直接查询 VictoriaTraces。"
      dependency="control"
      spacing="flush"
    >
      <Form
        form={form}
        layout="horizontal"
        labelCol={{ flex: '120px' }}
        wrapperCol={{ flex: '1 1 0' }}
        onFinish={(values) => void submit(values)}
      >
        <div className={styles.editor}>
          <Link href="/apm/events/policies" className={styles.editorTitle}>
            <ArrowLeftOutlined aria-hidden="true" />
            返回策略列表
          </Link>
          <div className={styles.editorLayout}>
            <div className={styles.editorMain}>
              <Steps direction="vertical" current={0} items={stepItems} />
              <div className={styles.editorFooter}>
                <Link href="/apm/events/policies"><Button>取消</Button></Link>
                {policyId ? (
                  <Popconfirm
                    title="确认删除该策略？"
                    description="删除后将停止后续评估，历史告警和事件快照不受影响。"
                    okText="删除"
                    cancelText="取消"
                    okButtonProps={{ danger: true, loading: deleting }}
                    onConfirm={() => void removePolicy()}
                  >
                    <Button danger icon={<DeleteOutlined />}>删除</Button>
                  </Popconfirm>
                ) : null}
                <Button type="primary" htmlType="submit" loading={saving}>
                  {policyId ? '保存策略' : '创建策略'}
                </Button>
              </div>
            </div>
            <aside className={styles.editorSide}>
              <section className={styles.sideSection}>
                <Typography.Title level={2}>模板变量</Typography.Title>
                <Table
                  size="small"
                  pagination={false}
                  rowKey="name"
                  columns={[
                    {
                      title: '变量',
                      dataIndex: 'name',
                      render: (value: string) => <code className={styles.variableCode}>{value}</code>,
                    },
                    { title: '说明', dataIndex: 'source' },
                    {
                      title: '操作',
                      dataIndex: 'name',
                      width: 64,
                      render: (value: string) => (
                        <Button type="link" size="small" aria-label={`复制 ${value}`} onClick={() => void copyVariable(value)}>
                          复制
                        </Button>
                      ),
                    },
                  ]}
                  dataSource={TEMPLATE_VARIABLES}
                />
              </section>
              <section className={styles.sideSection}>
                <div className={styles.previewHeading}>
                  <div>
                    <Typography.Title level={2}>指标预览</Typography.Title>
                    <Typography.Text type="secondary">
                      {METRICS.find((item) => item.value === metricType)?.label ?? metricType}（{thresholdUnit}） · {form.getFieldValue('metric_window') ?? 5} 分钟
                      {selectedScope.environment ? ` · ${selectedScope.environment}` : ''}
                      {previewing ? ' · 正在更新' : ' · 配置变化后自动刷新'}
                    </Typography.Text>
                  </div>
                  <Button type="link" loading={previewing} onClick={() => void runPreview()}>刷新</Button>
                </div>
                {preview ? (
                  <>
                    <Space className={styles.previewValue}>
                      <Typography.Text strong>
                        {preview.value === null
                          ? '无数据'
                          : metricType === 'error_rate'
                            ? `${Number(preview.value) * 100}%`
                            : preview.value}
                      </Typography.Text>
                      <Typography.Text type="secondary">
                        {preview.data_state === 'no_data'
                          ? 'VictoriaTraces 当前窗口无样本'
                          : dayjs(preview.evaluated_at).format('HH:mm:ss')}
                      </Typography.Text>
                    </Space>
                    <div className={styles.previewChart}>
                      <TimeSeriesComposedChart
                        data={previewRows}
                        xDataKey="timestamp"
                        getXLabel={(item) => dayjs(String(item.timestamp)).format('HH:mm')}
                        xAxisBoundaryGap={false}
                        series={[
                          {
                            name: METRICS.find((item) => item.value === metricType)?.label ?? metricType,
                            type: 'line',
                            dataKey: 'value',
                            color: OBSERVABILITY_SERIES_COLORS[0],
                            showArea: true,
                            areaOpacity: 0.36,
                            smooth: false,
                            lineWidth: 1,
                          },
                          {
                            name: '当前阈值',
                            type: 'line',
                            dataKey: 'threshold',
                            color: ALERT_LEVEL_COLORS[preview.threshold?.severity ?? 'critical'],
                            lineWidth: 1,
                          },
                        ]}
                      />
                    </div>
                  </>
                ) : (
                  <div className={styles.previewEmpty}>
                    <Typography.Text type="secondary" role="status">
                      {previewing
                        ? '正在查询真实指标趋势…'
                        : previewFailed
                          ? '自动预览暂不可用，可点击右上角刷新重试。'
                          : '选择服务并至少启用一个告警阈值后，将自动加载真实指标趋势。'}
                    </Typography.Text>
                  </div>
                )}
              </section>
            </aside>
          </div>
        </div>
      </Form>
    </ApmRouteShell>
  );
}
