'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  message,
  Select,
  Space,
  Steps,
  Table,
  Typography,
  theme,
} from 'antd';
import dayjs from 'dayjs';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState from '@/app/apm/components/catalog-state';
import TimeSeriesComposedChart from '@/components/time-series-composed-chart';
import { useTranslation } from '@/utils/i18n';
import type {
  ApmNotificationChannel,
  ApmPolicy,
  ApmPolicyInput,
  ApmPolicyMetric,
  ApmPolicyQueryResult,
  ApmService,
} from '@/app/apm/types';

const DEFAULT_VALUES: ApmPolicyInput = {
  name: '',
  service_id: '',
  environment: 'production',
  alert_name: '${service} ${metric} ${comparator} ${threshold}',
  endpoints: [],
  version_mode: 'all',
  versions: [],
  metric_type: 'error_rate',
  evaluation_interval: 1,
  metric_window: 5,
  aggregation: 'avg',
  thresholds: [{ severity: 'warning', comparator: 'gt', value: 0.05 }],
  trigger_after: 3,
  recover_after: 3,
  no_data_after: null,
  no_data_severity: '',
  notification_targets: [],
};

const METRICS: Array<{ value: ApmPolicyMetric; label: string }> = [
  { value: 'error_rate', label: '错误率' },
  { value: 'p95', label: 'P95 延迟' },
  { value: 'p99', label: 'P99 延迟' },
  { value: 'throughput', label: '吞吐量' },
  { value: 'no_traffic', label: '无流量' },
];

function toInput(policy: ApmPolicy): ApmPolicyInput {
  return {
    name: policy.name,
    service_id: policy.service_id,
    environment: policy.environment,
    alert_name: policy.alert_name,
    endpoints: policy.endpoints,
    version_mode: policy.version_mode,
    versions: policy.versions,
    metric_type: policy.metric_type,
    evaluation_interval: policy.evaluation_interval,
    metric_window: policy.metric_window,
    aggregation: policy.aggregation,
    thresholds: policy.thresholds,
    trigger_after: policy.trigger_after,
    recover_after: policy.recover_after,
    no_data_after: policy.no_data_after,
    no_data_severity: policy.no_data_severity,
    notification_targets: policy.notification_targets,
  };
}

export default function ApmPolicyEditor({ policyId }: { policyId?: string }) {
  const { t } = useTranslation();
  const router = useRouter();
  const { token } = theme.useToken();
  const {
    createPolicy,
    getInstances,
    getNotificationChannels,
    getPolicy,
    getServiceRed,
    getServices,
    isLoading,
    previewPolicy,
    updatePolicy,
  } = useApmApi();
  const [form] = Form.useForm<ApmPolicyInput>();
  const serviceId = Form.useWatch('service_id', form);
  const environment = Form.useWatch('environment', form);
  const versionMode = Form.useWatch('version_mode', form);
  const metricType = Form.useWatch('metric_type', form) ?? 'error_rate';
  const notificationTargets = Form.useWatch('notification_targets', form);
  const [services, setServices] = useState<ApmService[]>([]);
  const [channels, setChannels] = useState<ApmNotificationChannel[]>([]);
  const [loadedPolicy, setLoadedPolicy] = useState<ApmPolicy | null>(null);
  const [endpointOptions, setEndpointOptions] = useState<string[]>([]);
  const [versionOptions, setVersionOptions] = useState<string[]>([]);
  const [preview, setPreview] = useState<ApmPolicyQueryResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);

  useEffect(() => {
    if (isLoading) return;
    setLoading(true);
    Promise.all([getServices({ include_archived: true }), getNotificationChannels(), policyId ? getPolicy(policyId) : Promise.resolve(null)])
      .then(([serviceItems, channelItems, policy]) => {
        setServices(serviceItems);
        setChannels(channelItems);
        setLoadedPolicy(policy);
        form.setFieldsValue(policy ? toInput(policy) : DEFAULT_VALUES);
      })
      .finally(() => setLoading(false));
  }, [form, getNotificationChannels, getPolicy, getServices, isLoading, policyId]);

  useEffect(() => {
    const service = services.find((item) => item.id === serviceId);
    if (!service || !environment) {
      setEndpointOptions([]);
      setVersionOptions([]);
      return;
    }
    const endedAt = new Date();
    const startedAt = new Date(endedAt.getTime() - 60 * 60 * 1000);
    Promise.all([
      getServiceRed(service.id, environment, startedAt.toISOString(), endedAt.toISOString()),
      getInstances({ environment, status: 'active', page_size: 200 }),
    ])
      .then(([red, instances]) => {
        setEndpointOptions(red.top_endpoints.map((item) => item.endpoint));
        setVersionOptions(
          Array.from(
            new Set(
              instances
                .filter((item) => item.service_namespace === service.namespace && item.service_name === service.name)
                .map((item) => item.version)
                .filter(Boolean),
            ),
          ).sort(),
        );
      })
      .catch(() => {
        setEndpointOptions([]);
        setVersionOptions([]);
      });
  }, [environment, getInstances, getServiceRed, serviceId, services]);

  const serviceOptions = useMemo(() => {
    const activeOptions = services
      .filter((item) => !item.archived_at)
      .map((item) => ({
        value: item.id,
        label: item.namespace ? `${item.namespace} / ${item.name}` : item.name,
      }));
    if (!loadedPolicy || activeOptions.some((item) => item.value === loadedPolicy.service_id)) {
      return activeOptions;
    }
    const selectedService = services.find((item) => item.id === loadedPolicy.service_id);
    const selectedName = selectedService?.namespace
      ? `${selectedService.namespace} / ${selectedService.name}`
      : selectedService?.name || `${loadedPolicy.service_namespace} / ${loadedPolicy.service_name}`;
    return [
      ...activeOptions,
      {
        value: loadedPolicy.service_id,
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
    for (const target of notificationTargets || []) {
      if (options.some((item) => item.value === target.channel_id)) continue;
      const name = target.channel_name || t('apm.events.channel', '渠道 {id}', { id: target.channel_id });
      options.push({
        value: target.channel_id,
        label: t('apm.policies.unavailableChannelOption', '{name}（当前不可用）', { name }),
        disabled: true,
      });
    }
    return options;
  }, [channels, notificationTargets, t]);

  const channelRecipientModeMap = useMemo(() => {
    const map = new Map<number, ApmNotificationChannel['recipient_mode'] | undefined>();
    channels.forEach((item) => map.set(item.id, item.recipient_mode));
    (notificationTargets || []).forEach((item) => {
      if (!map.has(item.channel_id)) map.set(item.channel_id, item.recipient_mode);
    });
    return map;
  }, [channels, notificationTargets]);
  const hasAvailableChannel = channels.some((item) => item.availability === 'available');
  const previewRows = useMemo(
    () =>
      (preview?.series ?? []).map((point) => ({
        timestamp: point.timestamp,
        value:
          metricType === 'error_rate'
            ? Number(point.error_rate ?? 0)
            : metricType === 'p95'
              ? point.p95_ms
              : metricType === 'p99'
                ? point.p99_ms
                : point.request_rate,
        threshold: preview?.threshold ? Number(preview.threshold.value) : null,
      })),
    [metricType, preview],
  );

  const submit = async (values: ApmPolicyInput) => {
    setSaving(true);
    try {
      if (policyId) await updatePolicy(policyId, values);
      else await createPolicy(values);
      message.success(
        policyId ? '策略已更新；后续评估使用新配置，历史快照保持不变' : '策略已创建；后续启停只在列表操作',
      );
      router.push('/apm/events/policies');
    } finally {
      setSaving(false);
    }
  };

  const runPreview = async () => {
    const values = await form.validateFields();
    setPreviewing(true);
    try {
      setPreview(await previewPolicy(values));
    } finally {
      setPreviewing(false);
    }
  };

  if (loading)
    return (
      <ApmRouteShell
        title={policyId ? '编辑告警策略' : '新建告警策略'}
        description="正在加载 APM 策略编辑器"
        dependency="control"
      >
        <ApmSurface>
          <CatalogState kind="loading" />
        </ApmSurface>
      </ApmRouteShell>
    );

  return (
    <ApmRouteShell
      title={policyId ? '编辑告警策略' : '新建告警策略'}
      description="四步完成范围、指标、条件和通知配置；预览直接查询 VictoriaTraces。"
      dependency="control"
    >
      <Form form={form} layout="vertical" onFinish={(values) => void submit(values)}>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[220px_minmax(0,1fr)_360px]">
          <ApmSurface className="self-start xl:sticky xl:top-4">
            <Steps
              direction="vertical"
              current={0}
              items={[
                { title: '基本信息', description: 'Service 与身份范围' },
                { title: '指标定义', description: '窗口与聚合' },
                { title: '告警条件', description: '多级阈值与恢复' },
                { title: '通知配置', description: '可靠投递目标' },
              ]}
            />
          </ApmSurface>
          <Space direction="vertical" size="middle" className="w-full">
            <ApmSurface>
              <Typography.Title level={2} className="!text-base">
                1. 基本信息
              </Typography.Title>
              <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
                <Form.Item name="name" label="策略名称" rules={[{ required: true }]}>
                  <Input maxLength={256} />
                </Form.Item>
                <Form.Item name="alert_name" label="告警标题模板">
                  <Input maxLength={512} />
                </Form.Item>
                <Form.Item name="service_id" label="Service" rules={[{ required: true }]}>
                  <Select
                    showSearch
                    optionFilterProp="label"
                    options={serviceOptions}
                  />
                </Form.Item>
                <Form.Item name="environment" label="环境（必选）" rules={[{ required: true, whitespace: true }]}>
                  <Input maxLength={256} />
                </Form.Item>
                <Form.Item name="endpoints" label="端点（可多选）">
                  <Select
                    mode="multiple"
                    allowClear
                    options={endpointOptions.map((value) => ({ value, label: value }))}
                    placeholder="不选表示全部端点"
                  />
                </Form.Item>
                <Form.Item name="version_mode" label="版本维度" rules={[{ required: true }]}>
                  <Select
                    options={[
                      { value: 'all', label: '全部版本' },
                      { value: 'specific', label: '指定版本' },
                      { value: 'grouped', label: '按版本分别评估' },
                    ]}
                  />
                </Form.Item>
                {versionMode === 'specific' ? (
                  <Form.Item name="versions" label="指定版本" rules={[{ required: true, type: 'array', min: 1 }]}>
                    <Select mode="multiple" options={versionOptions.map((value) => ({ value, label: value }))} />
                  </Form.Item>
                ) : null}
              </div>
            </ApmSurface>
            <ApmSurface>
              <Typography.Title level={2} className="!text-base">
                2. 指标定义
              </Typography.Title>
              <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
                <Form.Item name="metric_type" label="APM 指标" rules={[{ required: true }]}>
                  <Select options={METRICS} />
                </Form.Item>
                <Form.Item name="evaluation_interval" label="执行周期（分钟）" rules={[{ required: true }]}>
                  <InputNumber min={1} max={60} className="!w-full" />
                </Form.Item>
                <Form.Item name="metric_window" label="指标窗口（分钟）" rules={[{ required: true }]}>
                  <InputNumber min={1} max={1440} className="!w-full" />
                </Form.Item>
                <Form.Item name="aggregation" label="聚合方式" rules={[{ required: true }]}>
                  <Select
                    options={[
                      { value: 'avg', label: '平均值' },
                      { value: 'max', label: '最大值' },
                      { value: 'min', label: '最小值' },
                      { value: 'last', label: '最新值' },
                    ]}
                  />
                </Form.Item>
              </div>
            </ApmSurface>
            <ApmSurface>
              <Typography.Title level={2} className="!text-base">
                3. 告警条件
              </Typography.Title>
              <Form.List name="thresholds">
                {(fields, { add, remove }) => (
                  <Space direction="vertical" className="w-full">
                    {fields.map((field) => (
                      <div key={field.key} className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr_1fr_auto]">
                        <Form.Item name={[field.name, 'severity']} rules={[{ required: true }]}>
                          <Select
                            placeholder="级别"
                            options={[
                              { value: 'critical', label: '严重' },
                              { value: 'error', label: '错误' },
                              { value: 'warning', label: '警告' },
                            ]}
                          />
                        </Form.Item>
                        <Form.Item name={[field.name, 'comparator']} rules={[{ required: true }]}>
                          <Select
                            options={[
                              { value: 'gt', label: '>' },
                              { value: 'gte', label: '≥' },
                              { value: 'lt', label: '<' },
                              { value: 'lte', label: '≤' },
                            ]}
                          />
                        </Form.Item>
                        <Form.Item name={[field.name, 'value']} rules={[{ required: true }]}>
                          <InputNumber className="!w-full" min={0} />
                        </Form.Item>
                        <Button
                          className="!min-h-11 !min-w-11"
                          aria-label="删除阈值"
                          danger
                          type="text"
                          icon={<DeleteOutlined />}
                          onClick={() => remove(field.name)}
                        />
                      </div>
                    ))}
                    <Button
                      disabled={fields.length >= 3}
                      icon={<PlusOutlined />}
                      onClick={() =>
                        add({
                          severity: 'error',
                          comparator: fields[0] ? form.getFieldValue(['thresholds', 0, 'comparator']) : 'gt',
                          value: 0,
                        })
                      }
                    >
                      添加阈值
                    </Button>
                  </Space>
                )}
              </Form.List>
              <div className="mt-4 grid grid-cols-1 gap-x-4 md:grid-cols-2">
                <Form.Item name="trigger_after" label="连续触发次数">
                  <InputNumber min={1} max={60} className="!w-full" />
                </Form.Item>
                <Form.Item name="recover_after" label="连续恢复次数">
                  <InputNumber min={1} max={60} className="!w-full" />
                </Form.Item>
                <Form.Item name="no_data_after" label="无数据持续次数">
                  <InputNumber min={1} max={60} className="!w-full" placeholder="留空关闭无数据告警" />
                </Form.Item>
                <Form.Item name="no_data_severity" label="无数据级别">
                  <Select
                    allowClear
                    options={[
                      { value: 'critical', label: '严重' },
                      { value: 'error', label: '错误' },
                      { value: 'warning', label: '警告' },
                    ]}
                  />
                </Form.Item>
              </div>
            </ApmSurface>
            <ApmSurface>
              <Typography.Title level={2} className="!text-base">
                4. 通知配置
              </Typography.Title>
              <Alert
                className="mb-4"
                showIcon
                type="info"
                message="通知记录独立于不可变事件快照；投递失败不会回滚 APM Alert/Event。"
              />
              <Form.List name="notification_targets">
                {(fields, { add, remove }) => (
                  <Space direction="vertical" className="w-full">
                    {fields.map((field) => {
                      const recipientMode = channelRecipientModeMap.get(notificationTargets?.[field.name]?.channel_id);
                      return (
                        <div key={field.key} className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_2fr_auto]">
                          <Form.Item
                            name={[field.name, 'channel_id']}
                            rules={[
                              { required: true },
                              {
                                validator: async (_, channelId) => {
                                  if (!channelId || channels.some((item) => item.id === channelId && item.availability === 'available')) return;
                                  throw new Error(t('apm.policies.invalidRemove', '已失效，保存前请移除'));
                                },
                              },
                            ]}
                          >
                            <Select
                              placeholder="通知渠道"
                              options={channelOptions}
                            />
                          </Form.Item>
                          <Form.Item
                            name={[field.name, 'recipients']}
                            hidden={recipientMode === 'none'}
                            rules={recipientMode === 'none' ? [] : [{ required: true }]}
                          >
                            <Select mode="tags" placeholder="接收人" />
                          </Form.Item>
                          <Button
                            className="!min-h-11 !min-w-11"
                            aria-label="删除通知渠道"
                            danger
                            type="text"
                            icon={<DeleteOutlined />}
                            onClick={() => remove(field.name)}
                          />
                        </div>
                      );
                    })}
                    <Button disabled={!hasAvailableChannel} icon={<PlusOutlined />} onClick={() => add({ recipients: [] })}>
                      添加渠道
                    </Button>
                  </Space>
                )}
              </Form.List>
            </ApmSurface>
            <div className="sticky bottom-0 z-10 flex justify-end gap-2 border-t border-[var(--color-border)] bg-[var(--color-bg)] py-3">
              <Link href="/apm/events/policies">
                <Button>取消</Button>
              </Link>
              <Button onClick={() => void runPreview()} loading={previewing}>
                预览真实指标
              </Button>
              <Button type="primary" htmlType="submit" loading={saving}>
                {policyId ? '保存策略' : '创建策略'}
              </Button>
            </div>
          </Space>
          <Space direction="vertical" size="middle" className="w-full self-start xl:sticky xl:top-4">
            <Card title="模板变量" size="small">
              <Table
                size="small"
                pagination={false}
                rowKey="name"
                columns={[
                  { title: '变量', dataIndex: 'name' },
                  { title: '来源', dataIndex: 'source' },
                ]}
                dataSource={[
                  { name: '${service}', source: 'Service 身份' },
                  { name: '${endpoint}', source: '端点身份' },
                  { name: '${environment}', source: '必选环境' },
                  { name: '${version}', source: '版本维度' },
                  { name: '${metric}', source: 'APM 指标' },
                  { name: '${threshold}', source: '所选级别阈值' },
                ]}
              />
            </Card>
            <Card
              title="真实指标预览"
              size="small"
              extra={
                <Button type="link" loading={previewing} onClick={() => void runPreview()}>
                  刷新
                </Button>
              }
            >
              {preview ? (
                <>
                  <Space className="mb-2">
                    <Typography.Text strong>{preview.value ?? '无数据'}</Typography.Text>
                    <Typography.Text type="secondary">
                      {preview.data_state === 'no_data'
                        ? 'VictoriaTraces 当前窗口无样本'
                        : dayjs(preview.evaluated_at).format('HH:mm:ss')}
                    </Typography.Text>
                  </Space>
                  <div className="h-56">
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
                          color: token.colorPrimary,
                          showArea: true,
                          showSymbol: true,
                        },
                        {
                          name: '当前阈值',
                          type: 'line',
                          dataKey: 'threshold',
                          color: token.colorError,
                          lineType: 'dashed',
                        },
                      ]}
                    />
                  </div>
                </>
              ) : (
                <Typography.Text type="secondary">
                  完成必填项后点击预览；数据来自 APM 接口与 VictoriaTraces。
                </Typography.Text>
              )}
            </Card>
          </Space>
        </div>
      </Form>
    </ApmRouteShell>
  );
}
