'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import Link from 'next/link';
import {
  Alert,
  Badge,
  Button,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  type TableColumnsType,
} from 'antd';
import useApmApi from '@/app/apm/api';
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

type PageState = CatalogStateKind | 'ready';
type ChannelState = 'loading' | 'ready' | 'empty' | 'error';

const METRIC_LABELS: Record<ApmPolicyMetric, string> = {
  error_rate: '错误率',
  p95: 'P95 延迟',
  p99: 'P99 延迟',
  throughput: '吞吐',
  no_traffic: '无流量',
};

const COMPARATOR_LABELS: Record<ApmPolicyComparator, string> = {
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
};

const SEVERITY_LABELS: Record<ApmPolicySeverity, string> = {
  critical: '严重',
  error: '错误',
  warning: '警告',
};

const DEFAULT_POLICY: Partial<ApmPolicyInput> = {
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
  const {
    createPolicy,
    deletePolicy,
    getPolicies,
    getNotificationChannels,
    getNotificationRecipients,
    getServices,
    isLoading: authLoading,
    setPolicyEnabled,
    testPolicy,
    updatePolicy,
  } = useApmApi();
  const [form] = Form.useForm<ApmPolicyInput>();
  const [policies, setPolicies] = useState<ApmPolicy[]>([]);
  const [services, setServices] = useState<ApmService[]>([]);
  const [notificationChannels, setNotificationChannels] = useState<ApmNotificationChannel[]>([]);
  const [notificationRecipients, setNotificationRecipients] = useState<ApmNotificationRecipient[]>([]);
  const [channelState, setChannelState] = useState<ChannelState>('loading');
  const [recipientState, setRecipientState] = useState<ChannelState>('loading');
  const [state, setState] = useState<PageState>('loading');
  const [editing, setEditing] = useState<ApmPolicy | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [keyword, setKeyword] = useState('');

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

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue(DEFAULT_POLICY as ApmPolicyInput);
    setModalOpen(true);
  };

  const openEdit = (policy: ApmPolicy) => {
    setEditing(policy);
    form.setFieldsValue({ ...policy, threshold: policy.threshold });
    setModalOpen(true);
  };

  const submit = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      if (editing) {
        await updatePolicy(editing.id, values);
        message.success('策略已更新');
      } else {
        await createPolicy(values);
        message.success('策略已创建');
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
      label: `${service.namespace || '未归类应用'} / ${service.name}`,
    })),
    [services]
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

  const columns: TableColumnsType<ApmPolicy> = [
    {
      title: '策略名称',
      dataIndex: 'name',
      render: (value) => <Typography.Text strong>{value}</Typography.Text>,
    },
    {
      title: '监控对象',
      render: (_, policy) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{policy.service_namespace || '未归类应用'} / {policy.service_name}</Typography.Text>
          <Typography.Text type="secondary" className="text-xs">{policy.environment || '未设置环境'}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '创建人',
      dataIndex: 'created_by',
      width: 120,
      responsive: ['md'],
      render: (value) => value || '—',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      responsive: ['lg'],
      render: (value) => <span className="tabular-nums">{dayjs(value).format('YYYY-MM-DD HH:mm')}</span>,
    },
    {
      title: '执行时间',
      width: 170,
      responsive: ['lg'],
      render: (_, policy) => policy.state?.last_succeeded_at
        ? <span className="tabular-nums">{dayjs(policy.state.last_succeeded_at).format('YYYY-MM-DD HH:mm')}</span>
        : <Typography.Text type="secondary">从未执行</Typography.Text>,
    },
    {
      title: '启停',
      width: 90,
      render: (_, policy) => (
        <Switch
          checked={policy.is_enabled}
          aria-label={`${policy.name}启用状态`}
          onChange={async (checked) => {
            await setPolicyEnabled(policy.id, checked);
            setPolicies((items) => items.map((item) => (
              item.id === policy.id ? { ...item, is_enabled: checked } : item
            )));
            message.success(checked ? '策略已启用' : '策略已停用');
          }}
        />
      ),
    },
    {
      title: '操作',
      width: 210,
      align: 'right',
      render: (_, policy) => (
        <Space wrap>
          <Button type="link" onClick={() => openEdit(policy)}>编辑</Button>
          <Button
            type="link"
            loading={testingId === policy.id}
            onClick={async () => {
              setTestingId(policy.id);
              try {
                const result = await testPolicy(policy.id);
                if (result.data_state === 'no_data') {
                  message.info('当前时间窗无数据，策略状态不会变化');
                } else {
                  message.info(`当前值 ${result.value}，${result.breached ? '已命中阈值' : '未命中阈值'}`);
                }
              } finally {
                setTestingId(null);
              }
            }}
          >
            测试查询
          </Button>
          <Popconfirm
            title="删除策略"
            description="删除后不再评估该策略，确认继续？"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={async () => {
              await deletePolicy(policy.id);
              message.success('策略已删除');
              load();
            }}
          >
            <Button type="link" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <ApmRouteShell
      title="告警策略"
      description="配置服务指标阈值与通知渠道，列表内可直接启停。"
      dependency="control"
    >
      <div className="flex flex-col gap-3">
        <ApmSurface padding="compact">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Badge
                count={policies.filter((policy) => policy.state?.status === 'firing').length}
                showZero
                color="var(--color-fail)"
              />
              <Typography.Text type="secondary" className="text-xs">
                告警中策略 · 每分钟评估，查询失败时保持上次状态
              </Typography.Text>
            </div>
            <Space wrap>
              <Input.Search
                allowClear
                aria-label="搜索策略"
                className="w-64"
                placeholder="搜索策略名称或监控对象"
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
              />
              <Button
                type="primary"
                icon={<PlusOutlined aria-hidden="true" />}
                onClick={openCreate}
                disabled={!services.length}
              >
                新建策略
              </Button>
            </Space>
          </div>
        </ApmSurface>
        <ApmSurface padding="none" className="overflow-hidden">
          {state === 'ready' ? (
            <Table
              rowKey="id"
              columns={columns}
              dataSource={filteredPolicies}
              pagination={{
                defaultPageSize: 20,
                pageSizeOptions: [10, 20, 50, 100],
                showSizeChanger: true,
                showTotal: (total) => `共 ${total} 条`,
              }}
            />
          ) : (
            <CatalogState
              kind={state}
              description={state === 'empty' ? (services.length ? '当前组织暂无 APM 策略。' : '请先接入并发现服务，再创建策略。') : undefined}
            />
          )}
        </ApmSurface>
      </div>
      <Modal
        title={editing ? '编辑 APM 策略' : '新建 APM 策略'}
        open={modalOpen}
        confirmLoading={saving}
        okText={editing ? '保存' : '创建'}
        cancelText="取消"
        onOk={submit}
        onCancel={() => {
          setModalOpen(false);
          form.resetFields();
        }}
        destroyOnHidden
        width={760}
        styles={{ body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' } }}
      >
        <Form form={form} layout="vertical" requiredMark>
          <Form.Item name="name" label="策略名称" rules={[{ required: true, message: '请输入策略名称' }]}>
            <Input maxLength={256} autoFocus />
          </Form.Item>
          <Form.Item name="service_id" label="服务" rules={[{ required: true, message: '请选择服务' }]}>
            <Select showSearch optionFilterProp="label" options={serviceOptions} />
          </Form.Item>
          <Form.Item name="environment" label="环境" tooltip="没有 deployment.environment 标签时可留空。">
            <Input maxLength={256} placeholder="production" />
          </Form.Item>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
            <Form.Item name="metric_type" label="指标" rules={[{ required: true }]}>
              <Select options={Object.entries(METRIC_LABELS).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item name="comparator" label="比较符" rules={[{ required: true }]}>
              <Select options={Object.entries(COMPARATOR_LABELS).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item
              name="threshold"
              label="阈值"
              tooltip="错误率使用 0–1 小数；延迟单位为毫秒；吞吐单位为请求/秒。"
              rules={[{ required: true, message: '请输入阈值' }]}
            >
              <InputNumber className="w-full" min={0} step={0.01} />
            </Form.Item>
          </div>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
            <Form.Item name="duration_window" label="连续命中次数" rules={[{ required: true }]}>
              <InputNumber className="w-full" min={1} max={1440} precision={0} />
            </Form.Item>
            <Form.Item name="recovery_window" label="连续恢复次数" rules={[{ required: true }]}>
              <InputNumber className="w-full" min={1} max={1440} precision={0} />
            </Form.Item>
            <Form.Item name="severity" label="告警级别" rules={[{ required: true }]}>
              <Select options={Object.entries(SEVERITY_LABELS).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
          </div>
          <Form.Item label="通知渠道" extra="渠道投递失败不会影响 APM 告警和事件持久化，可在事件页查看终态并人工重投。">
            {channelState === 'error' ? (
              <Alert
                type="warning"
                showIcon
                message="暂时无法读取系统通知渠道"
                description={(
                  <Space wrap>
                    <span>可以稍后重试，或前往系统管理检查渠道配置。</span>
                    <Button type="link" size="small" icon={<ReloadOutlined />} onClick={load}>重试</Button>
                    <Link href="/system-manager/channel">系统管理</Link>
                  </Space>
                )}
              />
            ) : channelState === 'empty' ? (
              <Alert
                type="info"
                showIcon
                message="当前组织没有可用通知渠道"
                description={<Link href="/system-manager/channel">前往系统管理配置渠道</Link>}
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
                  <Alert type="warning" showIcon message="系统用户目录暂不可用，已有配置可查看但暂不能新增接收人。" />
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
                          <Typography.Text strong>{channel?.name ?? snapshot?.channel_name ?? `渠道 ${target?.channel_id ?? ''}`}</Typography.Text>
                          <div className="mt-1 flex flex-wrap gap-1">
                            <Tag bordered={false}>{channel?.channel_type ?? snapshot?.channel_type ?? '未知类型'}</Tag>
                            <Tag bordered={false} color={deliveryMode === 'alert_event_copy' ? 'purple' : 'blue'}>
                              {deliveryMode === 'alert_event_copy' ? '告警中心事件副本' : '普通通知'}
                            </Tag>
                            {channelMissing ? <Tag bordered={false} color="error">已失效，保存前请移除</Tag> : null}
                          </div>
                        </div>
                        <Button type="text" danger icon={<DeleteOutlined />} aria-label="移除通知渠道" onClick={() => remove(field.name)} />
                      </div>
                      <Form.Item name={[field.name, 'channel_id']} hidden><InputNumber /></Form.Item>
                      <Form.Item
                        name={[field.name, 'recipients']}
                        label={recipientMode === 'system_user' ? '系统用户 ID' : '接收人'}
                        hidden={recipientMode === 'none'}
                        rules={recipientMode === 'none' ? [] : [
                          { required: true, message: '请填写至少一个接收人' },
                          ...(recipientMode === 'system_user' ? [{
                            validator: (_: unknown, values?: string[]) => (
                              (values ?? []).every((value) => /^\d+$/.test(value))
                                ? Promise.resolve()
                                : Promise.reject(new Error('系统用户必须填写数字 ID'))
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
                              .map((recipientId) => ({ value: recipientId, label: `用户 ${recipientId}（当前不可用）`, disabled: true })),
                          ] : undefined}
                          notFoundContent={recipientMode === 'system_user' && recipientState === 'error'
                            ? '系统用户目录暂不可用'
                            : undefined}
                          placeholder={recipientMode === 'system_user' ? '请选择系统用户' : '输入接收人，回车确认'}
                        />
                      </Form.Item>
                    </div>
                  );
                })}
                <Select
                  value={undefined}
                  loading={channelState === 'loading'}
                  disabled={channelState !== 'ready'}
                  placeholder="添加通知渠道"
                  options={notificationChannels
                    .filter((channel) => !fields.some((field) => (
                      form.getFieldValue(['notification_targets', field.name, 'channel_id']) === channel.id
                    )))
                    .map((channel) => ({
                      value: channel.id,
                      label: `${channel.name} · ${channel.delivery_mode === 'alert_event_copy' ? '告警中心副本' : channel.channel_type}`,
                    }))}
                  onChange={(channelId) => add({ channel_id: channelId, recipients: [] })}
                />
              </Space>
            )}
          </Form.List>
          <Form.Item name="is_enabled" label="创建后启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </ApmRouteShell>
  );
}
