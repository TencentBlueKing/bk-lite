'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeftOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Input, InputNumber, message, Select, Space, Switch, Typography } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState from '@/app/apm/components/catalog-state';
import type {
  ApmNotificationChannel,
  ApmPolicyComparator,
  ApmPolicyInput,
  ApmPolicyMetric,
  ApmPolicySeverity,
  ApmService,
} from '@/app/apm/types';
import { useTranslation } from '@/utils/i18n';

const METRIC_LABEL_KEYS: Record<ApmPolicyMetric, string> = {
  error_rate: 'apm.common.errorRate',
  p95: 'apm.common.p95Latency',
  p99: 'apm.common.p99Latency',
  throughput: 'apm.explore.throughputShort',
  no_traffic: 'apm.alerts.noTraffic',
};
const COMPARATORS: Record<ApmPolicyComparator, string> = { gt: '>', gte: '≥', lt: '<', lte: '≤' };
const SEVERITY_KEYS: Record<ApmPolicySeverity, string> = {
  critical: 'apm.severity.critical',
  error: 'apm.severity.error',
  warning: 'apm.severity.warning',
};

export default function ApmPolicyCreatePage() {
  const { t } = useTranslation();
  const router = useRouter();
  const { createPolicy, getNotificationChannels, getServices, isLoading } = useApmApi();
  const [form] = Form.useForm<ApmPolicyInput>();
  const notificationTargets = Form.useWatch('notification_targets', form);
  const [services, setServices] = useState<ApmService[]>([]);
  const [channels, setChannels] = useState<ApmNotificationChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const metricLabels: Record<ApmPolicyMetric, string> = {
    error_rate: t(METRIC_LABEL_KEYS.error_rate, '错误率'),
    p95: t(METRIC_LABEL_KEYS.p95, 'P95 延迟'),
    p99: t(METRIC_LABEL_KEYS.p99, 'P99 延迟'),
    throughput: t(METRIC_LABEL_KEYS.throughput, '吞吐'),
    no_traffic: t(METRIC_LABEL_KEYS.no_traffic, '无流量'),
  };
  const severityLabels: Record<ApmPolicySeverity, string> = {
    critical: t(SEVERITY_KEYS.critical, '严重'),
    error: t(SEVERITY_KEYS.error, '错误'),
    warning: t(SEVERITY_KEYS.warning, '警告'),
  };

  useEffect(() => {
    if (isLoading) return;
    setLoading(true);
    Promise.all([getServices(), getNotificationChannels()])
      .then(([serviceItems, channelItems]) => {
        setServices(serviceItems);
        setChannels(channelItems.filter((item) => item.availability === 'available'));
      })
      .finally(() => setLoading(false));
  }, [getNotificationChannels, getServices, isLoading]);

  const serviceOptions = useMemo(() => services.map((service) => ({
    value: service.id,
    label: service.namespace ? `${service.namespace} / ${service.name}` : service.name,
  })), [services]);
  const channelMap = useMemo(() => new Map(channels.map((channel) => [channel.id, channel])), [channels]);

  const submit = async (values: ApmPolicyInput) => {
    setSaving(true);
    try {
      await createPolicy(values);
      message.success(t('apm.policies.created', '策略已创建'));
      router.push('/apm/events/policies');
    } finally {
      setSaving(false);
    }
  };

  return (
    <ApmRouteShell title={t('apm.policies.createPageTitle', '新建告警策略')} description={t('apm.policies.createPageDescription', '按服务、触发条件和通知方式完整配置策略。')} dependency="control">
      {loading ? <ApmSurface><CatalogState kind="loading" /></ApmSurface> : (
        <Form<ApmPolicyInput>
          form={form}
          layout="vertical"
          initialValues={{
            environment: 'production',
            metric_type: 'error_rate',
            comparator: 'gt',
            threshold: 0.05,
            duration_window: 3,
            recovery_window: 3,
            severity: 'warning',
            notification_targets: [],
            is_enabled: true,
          }}
          onFinish={(values) => void submit(values)}
        >
          <div className="mx-auto flex max-w-5xl flex-col gap-3">
            <div className="flex justify-end">
              <Link href="/apm/events/policies"><Button icon={<ArrowLeftOutlined aria-hidden="true" />}>{t('apm.policies.backToList', '返回列表')}</Button></Link>
            </div>
            <ApmSurface>
              <Typography.Title level={2} className="!mb-4 !text-base">{t('apm.policies.basic', '基本信息')}</Typography.Title>
              <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
                <Form.Item name="name" label={t('apm.policies.name', '策略名称')} rules={[{ required: true, message: t('apm.policies.nameRequired', '请输入策略名称') }]}>
                  <Input maxLength={256} showCount placeholder={t('apm.policies.namePlaceholder', '例如：结算服务错误率过高')} />
                </Form.Item>
                <Form.Item name="severity" label={t('apm.policies.severity', '告警级别')} rules={[{ required: true }]}>
                  <Select options={Object.entries(severityLabels).map(([value, label]) => ({ value, label }))} />
                </Form.Item>
                <Form.Item name="service_id" label={t('apm.common.service', '服务')} rules={[{ required: true, message: t('apm.policies.serviceRequired', '请选择服务') }]}>
                  <Select showSearch optionFilterProp="label" options={serviceOptions} placeholder={t('apm.common.selectService', '选择服务')} />
                </Form.Item>
                <Form.Item name="environment" label={t('apm.common.environment', '环境')} rules={[{ required: true, whitespace: true, message: t('apm.policies.environmentRequired', '请输入环境') }]}>
                  <Input maxLength={256} placeholder="production" />
                </Form.Item>
              </div>
            </ApmSurface>

            <ApmSurface>
              <Typography.Title level={2} className="!mb-4 !text-base">{t('apm.policies.triggerRecover', '触发与恢复')}</Typography.Title>
              <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
                <Form.Item name="metric_type" label={t('apm.policies.metric', '指标')} rules={[{ required: true }]}>
                  <Select options={Object.entries(metricLabels).map(([value, label]) => ({ value, label }))} />
                </Form.Item>
                <Form.Item name="comparator" label={t('apm.policies.comparator', '比较符')} rules={[{ required: true }]}>
                  <Select options={Object.entries(COMPARATORS).map(([value, label]) => ({ value, label }))} />
                </Form.Item>
                <Form.Item name="threshold" label={t('apm.policies.threshold', '阈值')} rules={[{ required: true, message: t('apm.policies.thresholdRequired', '请输入阈值') }]}>
                  <InputNumber className="!w-full" min={0} step={0.01} />
                </Form.Item>
                <Form.Item name="duration_window" label={t('apm.policies.hits', '连续命中次数')} rules={[{ required: true }]}>
                  <InputNumber className="!w-full" min={1} max={1440} precision={0} />
                </Form.Item>
                <Form.Item name="recovery_window" label={t('apm.policies.recoveries', '连续恢复次数')} rules={[{ required: true }]}>
                  <InputNumber className="!w-full" min={1} max={1440} precision={0} />
                </Form.Item>
                <Form.Item name="is_enabled" label={t('apm.policies.enableOnCreate', '创建后启用')} valuePropName="checked">
                  <Switch />
                </Form.Item>
              </div>
              <Typography.Text type="secondary" className="!text-xs">{t('apm.policies.thresholdHint', '错误率使用 0–1 小数；时延单位为毫秒；吞吐单位为请求/秒。')}</Typography.Text>
            </ApmSurface>

            <ApmSurface>
              <Typography.Title level={2} className="!mb-1 !text-base">{t('apm.policies.notificationChannels', '通知渠道')}</Typography.Title>
              <Typography.Text type="secondary" className="mb-4 block !text-xs">{t('apm.policies.notificationHint', '通知失败不会影响告警事件持久化，可在告警详情中人工重投。')}</Typography.Text>
              {!channels.length ? <Alert showIcon type="info" message={t('apm.policies.noChannels', '当前没有可用通知渠道，可不配置直接创建策略。')} /> : null}
              <Form.List name="notification_targets">
                {(fields, { add, remove }) => (
                  <Space direction="vertical" className="w-full" size="middle">
                    {fields.map((field) => {
                      const channelId = notificationTargets?.[field.name]?.channel_id;
                      const channel = channelMap.get(channelId);
                      return (
                        <div key={field.key} className="grid grid-cols-1 gap-x-3 rounded-lg border border-[var(--color-border)] p-3 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto]">
                          <Form.Item name={[field.name, 'channel_id']} label={t('apm.policies.channel', '渠道')} rules={[{ required: true }]}>
                            <Select options={channels.map((item) => ({ value: item.id, label: item.name }))} />
                          </Form.Item>
                          <Form.Item
                            name={[field.name, 'recipients']}
                            label={t('apm.policies.recipients', '接收人')}
                            hidden={channel?.recipient_mode === 'none'}
                            rules={channel?.recipient_mode === 'none' ? [] : [{ required: true, message: t('apm.policies.recipientsRequired', '请填写接收人') }]}
                          >
                            <Select mode="tags" tokenSeparators={[',', ' ']} maxCount={100} placeholder={t('apm.policies.recipientsPlaceholder', '输入接收人，回车确认')} />
                          </Form.Item>
                          <Button className="mt-7" danger type="text" aria-label={t('apm.policies.removeChannel', '移除渠道')} icon={<DeleteOutlined aria-hidden="true" />} onClick={() => remove(field.name)} />
                        </div>
                      );
                    })}
                    <Button disabled={!channels.length} icon={<PlusOutlined aria-hidden="true" />} onClick={() => add({ recipients: [] })}>{t('apm.policies.addChannel', '添加通知渠道')}</Button>
                  </Space>
                )}
              </Form.List>
            </ApmSurface>

            <div className="sticky bottom-0 flex justify-end gap-2 border-t border-[var(--color-border)] bg-[var(--color-bg)] py-3">
              <Link href="/apm/events/policies"><Button disabled={saving}>{t('common.cancel', '取消')}</Button></Link>
              <Button htmlType="submit" type="primary" loading={saving}>{t('apm.policies.createAction', '创建策略')}</Button>
            </div>
          </div>
        </Form>
      )}
    </ApmRouteShell>
  );
}
