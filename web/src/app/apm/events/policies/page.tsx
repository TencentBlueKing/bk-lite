'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { DeleteOutlined, PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import Link from 'next/link';
import {
  Alert,
  Button,
  Form,
  Grid,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
  type TableColumnsType,
} from 'antd';
import useApmApi from '@/app/apm/api';
import ApmDataTable, { APM_TABLE_COLUMN_WIDTHS } from '@/app/apm/components/apm-data-table';
import dayjs from 'dayjs';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import type {
  ApmPolicy,
  ApmPolicyComparator,
  ApmPolicyInput,
  ApmPolicyMetric,
  ApmPolicySeverity,
  ApmService,
  ApmNotificationChannel,
  ApmNotificationRecipient,
  ApmPolicyNotificationTarget,
} from '@/app/apm/types';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import FilterToolbar from '@/components/filter-toolbar';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';
type ChannelState = 'loading' | 'ready' | 'empty' | 'error';

const METRIC_LABEL_KEYS: Record<ApmPolicyMetric, string> = {
  error_rate: 'apm.common.errorRate',
  p95: 'apm.common.p95Latency',
  p99: 'apm.common.p99Latency',
  throughput: 'apm.explore.throughputShort',
  no_traffic: 'apm.alerts.noTraffic',
};

const COMPARATOR_LABELS: Record<ApmPolicyComparator, string> = {
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
};

const SEVERITY_KEYS: Record<ApmPolicySeverity, string> = {
  critical: 'apm.severity.critical',
  error: 'apm.severity.error',
  warning: 'apm.severity.warning',
};

const DEFAULT_POLICY_VALUES: ApmPolicyInput = {
  name: '',
  service_id: '',
  environment: 'production',
  metric_type: 'error_rate',
  comparator: 'gt',
  threshold: 0.05,
  duration_window: 3,
  recovery_window: 3,
  severity: 'warning',
  notification_targets: [],
  is_enabled: true,
};

export default function ApmPoliciesPage() {
  const { t } = useTranslation();
  const screens = Grid.useBreakpoint();
  const {
    createPolicy,
    deletePolicy,
    getPolicies,
    getNotificationChannels,
    getNotificationRecipients,
    getServices,
    isLoading: authLoading,
    setPolicyEnabled,
    updatePolicy,
  } = useApmApi();
  const [form] = Form.useForm<ApmPolicyInput>();
  const [policies, setPolicies] = useState<ApmPolicy[]>([]);
  const [services, setServices] = useState<ApmService[]>([]);
  const [notificationChannels, setNotificationChannels] = useState<ApmNotificationChannel[]>([]);
  const [notificationRecipients, setNotificationRecipients] = useState<ApmNotificationRecipient[]>([]);
  const [channelState, setChannelState] = useState<ChannelState>('loading');
  const [channelRetrying, setChannelRetrying] = useState(false);
  const [recipientState, setRecipientState] = useState<ChannelState>('loading');
  const [state, setState] = useState<PageState>('loading');
  const [editing, setEditing] = useState<ApmPolicy | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [mutatingId, setMutatingId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

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

  const load = useCallback(() => {
    if (authLoading) return;
    setState('loading');
    setChannelState('loading');
    getNotificationChannels()
      .then((items) => {
        setNotificationChannels(items);
        setChannelState(items.length ? 'ready' : 'empty');
      })
      .catch(() => {
        setNotificationChannels([]);
        setChannelState('error');
      });
    setRecipientState('loading');
    getNotificationRecipients({ limit: 100 })
      .then((items) => {
        setNotificationRecipients(items);
        setRecipientState(items.length ? 'ready' : 'empty');
      })
      .catch(() => {
        setNotificationRecipients([]);
        setRecipientState('error');
      });
    Promise.all([getPolicies(), getServices()])
      .then(([policyItems, serviceItems]) => {
        setPolicies(policyItems);
        setServices(serviceItems);
        setState(policyItems.length ? 'ready' : 'empty');
      })
      .catch((error) => setState(catalogErrorKind(error)));
  }, [authLoading, getNotificationChannels, getNotificationRecipients, getPolicies, getServices]);

  useEffect(() => load(), [load]);

  const retryChannels = async () => {
    if (channelRetrying) return;
    setChannelRetrying(true);
    try {
      const items = await getNotificationChannels();
      setNotificationChannels(items);
      setChannelState(items.length ? 'ready' : 'empty');
    } catch {
      setChannelState('error');
    } finally {
      setChannelRetrying(false);
    }
  };

  const openEdit = (policy: ApmPolicy) => {
    setEditing(policy);
    form.resetFields();
    form.setFieldsValue({ ...policy, threshold: policy.threshold });
    setModalOpen(true);
  };

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue(DEFAULT_POLICY_VALUES);
    setModalOpen(true);
  };

  const submit = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await updatePolicy(editing.id, values);
        message.success(t('apm.policies.updated', '策略已更新'));
      } else {
        await createPolicy(values);
        message.success(t('apm.policies.created', '策略已创建'));
      }
      setModalOpen(false);
      form.resetFields();
      load();
    } finally {
      setSaving(false);
    }
  };

  const serviceOptions = useMemo(
    () => services.map((service) => ({
      value: service.id,
      label: `${service.namespace || t('apm.common.unsetNamespace', '未设置 namespace')} / ${service.name}`,
    })),
    [services, t]
  );

  const channelById = useMemo(
    () => new Map(notificationChannels.map((channel) => [channel.id, channel])),
    [notificationChannels]
  );

  const filteredPolicies = useMemo(() => {
    const normalized = keyword.trim().toLocaleLowerCase();
    if (!normalized) return policies;
    return policies.filter((policy) => (
      policy.name.toLocaleLowerCase().includes(normalized)
      || policy.service_name.toLocaleLowerCase().includes(normalized)
      || policy.service_namespace.toLocaleLowerCase().includes(normalized)
    ));
  }, [keyword, policies]);
  const pagePolicies = useMemo(
    () => filteredPolicies.slice((page - 1) * pageSize, page * pageSize),
    [filteredPolicies, page, pageSize],
  );

  const removePolicy = async (policy: ApmPolicy) => {
    setMutatingId(policy.id);
    try {
      await deletePolicy(policy.id);
      message.success(t('apm.policies.deleted', '策略已删除'));
      load();
    } finally {
      setMutatingId(null);
    }
  };

  const columns: TableColumnsType<ApmPolicy> = [
    {
      title: t('apm.policies.name', '策略名称'),
      dataIndex: 'name',
      render: (value) => <EllipsisWithTooltip className="truncate font-medium" text={value} />,
    },
    {
      title: t('apm.policies.creator', '创建者'),
      dataIndex: 'created_by',
      width: 144,
      responsive: ['lg'],
      render: (value) => value || '—',
    },
    {
      title: t('apm.policies.createdAt', '创建时间'),
      dataIndex: 'created_at',
      width: APM_TABLE_COLUMN_WIDTHS.timestamp,
      responsive: ['xl'],
      render: (value) => <span className="tabular-nums">{dayjs(value).format('YYYY-MM-DD HH:mm')}</span>,
    },
    {
      title: t('apm.policies.lastRun', '最近执行'),
      width: APM_TABLE_COLUMN_WIDTHS.timestamp,
      responsive: ['xxl'],
      render: (_, policy) => policy.state?.last_succeeded_at
        ? <span className="tabular-nums">{dayjs(policy.state.last_succeeded_at).format('YYYY-MM-DD HH:mm')}</span>
        : <Typography.Text type="secondary">{t('apm.policies.neverRun', '从未执行')}</Typography.Text>,
    },
    {
      title: t('apm.policies.enabled', '启用状态'),
      width: APM_TABLE_COLUMN_WIDTHS.status,
      align: 'center',
      render: (_, policy) => (
        <Switch
          checked={policy.is_enabled}
          aria-label={t('apm.policies.enabledAria', '{name}启用状态', { name: policy.name })}
          loading={mutatingId === policy.id}
          disabled={mutatingId !== null && mutatingId !== policy.id}
          onChange={async (checked) => {
            setMutatingId(policy.id);
            try {
              await setPolicyEnabled(policy.id, checked);
              setPolicies((items) => items.map((item) => (
                item.id === policy.id ? { ...item, is_enabled: checked } : item
              )));
              message.success(checked ? t('apm.policies.enabledToast', '策略已启用') : t('apm.policies.disabledToast', '策略已停用'));
            } finally {
              setMutatingId(null);
            }
          }}
        />
      ),
    },
    {
      title: t('apm.common.operation', '操作'),
      key: 'action',
      width: screens.sm ? APM_TABLE_COLUMN_WIDTHS.metricWide : APM_TABLE_COLUMN_WIDTHS.singleAction,
      align: 'right',
      fixed: 'right',
      render: (_, policy) => screens.sm ? (
        <Space className="whitespace-nowrap" size={8}>
          <Button
            className="!px-0"
            disabled={mutatingId !== null}
            size="small"
            type="link"
            onClick={() => openEdit(policy)}
          >
            {t('common.edit', '编辑')}
          </Button>
          <Popconfirm
            cancelText={t('common.cancel', '取消')}
            description={t('apm.policies.deleteHint', '删除后不再评估该策略，且无法恢复。')}
            okButtonProps={{ danger: true, loading: mutatingId === policy.id }}
            okText={t('common.delete', '删除')}
            title={t('apm.policies.deleteConfirm', '确认删除这个策略？')}
            onConfirm={() => removePolicy(policy)}
          >
            <Button className="!px-0" danger disabled={mutatingId !== null} size="small" type="link">
              {t('common.delete', '删除')}
            </Button>
          </Popconfirm>
        </Space>
      ) : (
        <MoreActionsDropdown
          ariaLabel={t('apm.serviceDetail.moreActions', '更多操作')}
          buttonType="link"
          items={[
            {
              key: 'edit',
              disabled: mutatingId !== null,
              label: t('common.edit', '编辑'),
              onClick: () => openEdit(policy),
            },
            {
              key: 'delete',
              danger: true,
              disabled: mutatingId !== null,
              label: t('common.delete', '删除'),
              confirm: {
                title: t('apm.policies.deleteConfirm', '确认删除这个策略？'),
                content: t('apm.policies.deleteHint', '删除后不再评估该策略，且无法恢复。'),
                okText: t('common.delete', '删除'),
                cancelText: t('common.cancel', '取消'),
              },
              onClick: () => removePolicy(policy),
            },
          ]}
          stopPropagation
        />
      ),
    },
  ];

  return (
    <ApmRouteShell
      title={t('apm.policies.title', '告警策略')}
      description={t('apm.policies.description', '配置服务指标阈值与通知渠道，列表内可直接启停。')}
      dependency="control"
    >
      <ApmSurface>
        <div className="flex flex-col gap-4">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
            <Input
              allowClear
              aria-label={t('apm.policies.search', '搜索策略')}
              className="min-w-0 flex-1 md:max-w-sm"
              prefix={<SearchOutlined aria-hidden="true" />}
              placeholder={t('apm.policies.searchName', '搜索策略名称')}
              value={keyword}
              onChange={(event) => { setKeyword(event.target.value); setPage(1); }}
            />
            <Space className="ml-auto">
              <Button icon={<ReloadOutlined aria-hidden="true" />} loading={state === 'loading'} onClick={load}>{t('common.refresh', '刷新')}</Button>
              <Button type="primary" icon={<PlusOutlined aria-hidden="true" />} disabled={!services.length} onClick={openCreate}>{t('apm.policies.new', '新建策略')}</Button>
            </Space>
          </FilterToolbar>
          {state === 'ready' ? (
            <ApmDataTable
              rowKey="id"
              columns={columns}
              dataSource={pagePolicies}
              headerAlignment="column"
              pagination={{
                current: page,
                pageSize,
                total: filteredPolicies.length,
                pageSizeOptions: [10, 20, 50, 100],
                showSizeChanger: true,
                onChange: (nextPage, nextPageSize) => {
                  setPage(nextPageSize === pageSize ? nextPage : 1);
                  setPageSize(nextPageSize);
                },
              }}
            />
          ) : (
            <CatalogState
              kind={state}
              description={state === 'empty' ? (services.length ? t('apm.policies.empty', '当前组织暂无 APM 策略。') : t('apm.policies.needServices', '请先接入并发现服务，再创建策略。')) : undefined}
              action={state === 'empty' && services.length ? <Button type="primary" onClick={openCreate}>{t('apm.policies.new', '新建策略')}</Button> : undefined}
              onRetry={state === 'forbidden' ? undefined : load}
            />
          )}
        </div>
      </ApmSurface>
      <Modal
        title={editing ? t('apm.policies.editTitle', '编辑 APM 策略') : t('apm.policies.createTitle', '新建 APM 策略')}
        open={modalOpen}
        confirmLoading={saving}
        okText={editing ? t('common.save', '保存') : t('common.create', '创建')}
        cancelText={t('common.cancel', '取消')}
        onOk={submit}
        onCancel={() => {
          setModalOpen(false);
          form.resetFields();
        }}
        destroyOnHidden
        width="min(760px, calc(100vw - 32px))"
        styles={{ body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' } }}
      >
        <Form form={form} layout="vertical" requiredMark>
          <Form.Item name="name" label={t('apm.policies.name', '策略名称')} rules={[{ required: true, message: t('apm.policies.nameRequired', '请输入策略名称') }]}>
            <Input maxLength={256} autoFocus />
          </Form.Item>
          <Form.Item name="service_id" label={t('apm.common.service', '服务')} rules={[{ required: true, message: t('apm.policies.serviceRequired', '请选择服务') }]}>
            <Select showSearch optionFilterProp="label" options={serviceOptions} />
          </Form.Item>
          <Form.Item name="environment" label={t('apm.common.environment', '环境')} tooltip={t('apm.policies.environmentHint', '没有 deployment.environment 标签时可留空。')}>
            <Input maxLength={256} placeholder="production" />
          </Form.Item>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
            <Form.Item name="metric_type" label={t('apm.policies.metric', '指标')} rules={[{ required: true }]}>
              <Select options={Object.entries(metricLabels).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item name="comparator" label={t('apm.policies.comparator', '比较符')} rules={[{ required: true }]}>
              <Select options={Object.entries(COMPARATOR_LABELS).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item
              name="threshold"
              label={t('apm.policies.threshold', '阈值')}
              tooltip={t('apm.policies.thresholdHintShort', '错误率使用 0–1 小数；延迟单位为毫秒；吞吐单位为请求/秒。')}
              rules={[{ required: true, message: t('apm.policies.thresholdRequired', '请输入阈值') }]}
            >
              <InputNumber className="w-full" min={0} step={0.01} />
            </Form.Item>
          </div>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
            <Form.Item name="duration_window" label={t('apm.policies.hits', '连续命中次数')} rules={[{ required: true }]}>
              <InputNumber className="w-full" min={1} max={1440} precision={0} />
            </Form.Item>
            <Form.Item name="recovery_window" label={t('apm.policies.recoveries', '连续恢复次数')} rules={[{ required: true }]}>
              <InputNumber className="w-full" min={1} max={1440} precision={0} />
            </Form.Item>
            <Form.Item name="severity" label={t('apm.policies.severity', '告警级别')} rules={[{ required: true }]}>
              <Select options={Object.entries(severityLabels).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
          </div>
          <Form.Item label={t('apm.policies.notificationChannels', '通知渠道')} extra={t('apm.policies.notificationHintList', '渠道投递失败不会影响 APM 告警和事件持久化，可在事件页查看终态并人工重投。')}>
            {channelState === 'error' ? (
              <Alert
                type="warning"
                showIcon
                message={t('apm.policies.channelsUnavailable', '暂时无法读取系统通知渠道')}
                description={(
                  <Space wrap>
                    <span>{t('apm.policies.retryChannels', '可以稍后重试，或前往系统管理检查渠道配置。')}</span>
                    <Button type="link" size="small" icon={<ReloadOutlined aria-hidden="true" />} loading={channelRetrying} onClick={retryChannels}>{t('common.retry', '重试')}</Button>
                    <Link href="/system-manager/channel">{t('apm.policies.systemManager', '系统管理')}</Link>
                  </Space>
                )}
              />
            ) : channelState === 'empty' ? (
              <Alert
                type="info"
                showIcon
                message={t('apm.policies.noOrgChannels', '当前组织没有可用通知渠道')}
                description={<Link href="/system-manager/channel">{t('apm.policies.goConfigureChannels', '前往系统管理配置渠道')}</Link>}
              />
            ) : null}
          </Form.Item>
          <Form.List name="notification_targets">
            {(fields, { add, remove }) => (
              <Space direction="vertical" className="w-full" size="middle">
                {fields.some((field) => {
                  const channelId = form.getFieldValue(['notification_targets', field.name, 'channel_id']);
                  return channelById.get(channelId)?.recipient_mode === 'system_user';
                }) && recipientState === 'error' ? (
                  <Alert type="warning" showIcon message={t('apm.policies.userDirectoryUnavailable', '系统用户目录暂不可用，已有配置可查看但暂不能新增接收人。')} />
                  ) : null}
                {fields.map((field) => {
                  const target = form.getFieldValue(['notification_targets', field.name]) as ApmPolicyNotificationTarget | undefined;
                  const channel = target ? channelById.get(target.channel_id) : undefined;
                  const snapshot = editing?.notification_targets.find((item) => item.channel_id === target?.channel_id);
                  const recipientMode = channel?.recipient_mode ?? snapshot?.recipient_mode;
                  const deliveryMode = channel?.delivery_mode ?? snapshot?.delivery_mode;
                  const channelMissing = Boolean(target?.channel_id && !channel && channelState !== 'loading');
                  return (
                    <div key={field.key} className="rounded-md border border-[var(--color-border-2)] p-3">
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div>
                          <Typography.Text strong>{channel?.name ?? snapshot?.channel_name ?? t('apm.alerts.channel', '渠道 {id}', { id: target?.channel_id ?? '' })}</Typography.Text>
                          <div className="mt-1 flex flex-wrap gap-1">
                            <Tag bordered={false}>{channel?.channel_type ?? snapshot?.channel_type ?? t('apm.alerts.unknownType', '未知类型')}</Tag>
                            <Tag bordered={false} color={deliveryMode === 'alert_event_copy' ? 'purple' : 'blue'}>
                              {deliveryMode === 'alert_event_copy'
                                ? t('apm.alerts.alertCopy', '告警中心事件副本')
                                : t('apm.alerts.plainNotice', '普通通知')}
                            </Tag>
                            {channelMissing ? <Tag bordered={false} color="error">{t('apm.policies.invalidRemove', '已失效，保存前请移除')}</Tag> : null}
                          </div>
                        </div>
                        <Button type="text" danger icon={<DeleteOutlined aria-hidden="true" />} aria-label={t('apm.policies.removeNotificationChannel', '移除通知渠道')} onClick={() => remove(field.name)} />
                      </div>
                      <Form.Item name={[field.name, 'channel_id']} hidden><InputNumber /></Form.Item>
                      <Form.Item
                        name={[field.name, 'recipients']}
                        label={recipientMode === 'system_user' ? t('apm.policies.userId', '系统用户 ID') : t('apm.policies.recipients', '接收人')}
                        hidden={recipientMode === 'none'}
                        rules={recipientMode === 'none' ? [] : [
                          { required: true, message: t('apm.policies.recipientsAtLeastOne', '请填写至少一个接收人') },
                          ...(recipientMode === 'system_user' ? [{
                            validator: (_: unknown, values?: string[]) => (
                              (values ?? []).every((value) => /^\d+$/.test(value))
                                ? Promise.resolve()
                                : Promise.reject(new Error(t('apm.policies.userIdNumeric', '系统用户必须填写数字 ID')))
                            ),
                          }] : []),
                        ]}
                        className="mb-0"
                      >
                        <Select
                          mode={recipientMode === 'system_user' ? 'multiple' : 'tags'}
                          tokenSeparators={[',', ' ']}
                          maxCount={100}
                          loading={recipientMode === 'system_user' && recipientState === 'loading'}
                          options={recipientMode === 'system_user' ? [
                            ...notificationRecipients.map((recipient) => ({
                              value: String(recipient.id),
                              label: recipient.display_name
                                ? `${recipient.display_name} (${recipient.username})`
                                : recipient.username,
                            })),
                            ...(target?.recipients ?? [])
                              .filter((recipientId) => !notificationRecipients.some((recipient) => String(recipient.id) === recipientId))
                              .map((recipientId) => ({ value: recipientId, label: t('apm.policies.userUnavailable', '用户 {id}（当前不可用）', { id: recipientId }), disabled: true })),
                          ] : undefined}
                          notFoundContent={recipientMode === 'system_user' && recipientState === 'error'
                            ? t('apm.policies.userDirectoryDown', '系统用户目录暂不可用')
                            : undefined}
                          placeholder={recipientMode === 'system_user' ? t('apm.policies.selectSystemUser', '请选择系统用户') : t('apm.policies.recipientsPlaceholder', '输入接收人，回车确认')}
                        />
                      </Form.Item>
                    </div>
                  );
                })}
                <Select
                  value={undefined}
                  loading={channelState === 'loading'}
                  disabled={channelState !== 'ready'}
                  placeholder={t('apm.policies.addChannel', '添加通知渠道')}
                  options={notificationChannels
                    .filter((channel) => !fields.some((field) => (
                      form.getFieldValue(['notification_targets', field.name, 'channel_id']) === channel.id
                    )))
                    .map((channel) => ({
                      value: channel.id,
                      label: `${channel.name} · ${channel.delivery_mode === 'alert_event_copy' ? t('apm.policies.alertCopyShort', '告警中心副本') : channel.channel_type}`,
                    }))}
                  onChange={(channelId) => add({ channel_id: channelId, recipients: [] })}
                />
              </Space>
            )}
          </Form.List>
          <Form.Item name="is_enabled" label={t('apm.policies.enableOnCreate', '创建后启用')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </ApmRouteShell>
  );
}
