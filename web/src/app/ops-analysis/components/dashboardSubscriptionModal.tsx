'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  message,
  Popconfirm,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { PlusOutlined } from '@ant-design/icons';

import { useDashboardSubscriptionApi } from '@/app/ops-analysis/api/dashboardSubscription';
import type {
  DashboardExecutionCreated,
  DashboardExecutionStatus,
  DashboardExecutionSummary,
  DashboardScheduleType,
  DashboardSubscription,
  DashboardSubscriptionStatus,
} from '@/app/ops-analysis/types/dashboardSubscription';
import { useChannelApi } from '@/app/system-manager/api/channel';
import { useTranslation } from '@/utils/i18n';

interface DashboardSubscriptionModalProps {
  open: boolean;
  /** @deprecated Prefer resourceType + resourceId; kept for Dashboard callers */
  dashboardId?: number;
  resourceType?: 'dashboard' | 'screen';
  resourceId?: number;
  appliedFilterValues?: Record<string, unknown>;
  onClose: () => void;
}

interface SubscriptionFormValues {
  name: string;
  recipient_email: string;
  email_channel?: number;
  status: DashboardSubscriptionStatus;
  schedule_type?: DashboardScheduleType | null;
  schedule_hour?: number | null;
  schedule_minute?: number | null;
  schedule_weekday?: number | null;
  schedule_day_of_month?: number | null;
  timezone?: string | null;
}

interface EmailChannelOption {
  id: number;
  name: string;
}

const normalizeChannelList = (response: unknown): EmailChannelOption[] => {
  const payload = response as
    | EmailChannelOption[]
    | {
        items?: unknown[];
        results?: unknown[];
        data?:
          | unknown[]
          | {
              items?: unknown[];
              results?: unknown[];
            };
      }
    | null
    | undefined;

  const rawItems: unknown[] = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.items)
      ? payload.items
      : Array.isArray(payload?.results)
        ? payload.results
        : Array.isArray(payload?.data)
          ? payload.data
          : Array.isArray(payload?.data?.items)
            ? payload.data.items
            : Array.isArray(payload?.data?.results)
              ? payload.data.results
              : [];

  return rawItems
    .filter(
      (item): item is Record<string, unknown> =>
        typeof item === 'object' && item !== null,
    )
    .filter((item) => item.channel_type === 'email')
    .map((item) => ({
      id: Number(item.id),
      name: String(item.name ?? item.display_name ?? ''),
    }))
    .filter((item) => item.name && !Number.isNaN(item.id));
};

const WEEKDAY_LABEL_KEYS = [
  'dashboard.subscriptionWeekdayMon',
  'dashboard.subscriptionWeekdayTue',
  'dashboard.subscriptionWeekdayWed',
  'dashboard.subscriptionWeekdayThu',
  'dashboard.subscriptionWeekdayFri',
  'dashboard.subscriptionWeekdaySat',
  'dashboard.subscriptionWeekdaySun',
] as const;

const padScheduleTime = (hour: number, minute: number): string =>
  `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;

type TranslateFn = (
  id: string,
  defaultMessage?: string,
  values?: Record<string, string | number>,
) => string;

export const formatSubscriptionScheduleSummary = (
  subscription: Pick<
    DashboardSubscription,
    | 'schedule_type'
    | 'schedule_hour'
    | 'schedule_minute'
    | 'schedule_weekday'
    | 'schedule_day_of_month'
  >,
  t: TranslateFn,
): string | null => {
  if (
    !subscription.schedule_type
    || subscription.schedule_hour == null
    || subscription.schedule_minute == null
  ) {
    return null;
  }
  const time = padScheduleTime(
    subscription.schedule_hour,
    subscription.schedule_minute,
  );
  if (subscription.schedule_type === 'daily') {
    return t('dashboard.subscriptionScheduleSummaryDaily', undefined, {
      time,
    });
  }
  if (subscription.schedule_type === 'weekly') {
    const weekdayIndex = Math.min(
      Math.max(subscription.schedule_weekday ?? 0, 0),
      6,
    );
    return t('dashboard.subscriptionScheduleSummaryWeekly', undefined, {
      weekday: t(WEEKDAY_LABEL_KEYS[weekdayIndex]),
      time,
    });
  }
  return t('dashboard.subscriptionScheduleSummaryMonthly', undefined, {
    day: subscription.schedule_day_of_month ?? 1,
    time,
  });
};

const isInFlightExecutionStatus = (
  status: DashboardExecutionStatus | undefined,
): boolean => status === 'pending' || status === 'running';

export const hasInFlightSubscriptionExecution = (
  subscription: Pick<
    DashboardSubscription,
    'latest_scheduled_execution' | 'latest_manual_test_execution'
  >,
): boolean =>
  isInFlightExecutionStatus(subscription.latest_scheduled_execution?.status)
  || isInFlightExecutionStatus(
    subscription.latest_manual_test_execution?.status,
  );

const DashboardSubscriptionModal = ({
  open,
  dashboardId,
  resourceType = 'dashboard',
  resourceId,
  appliedFilterValues = {},
  onClose,
}: DashboardSubscriptionModalProps) => {
  const resolvedResourceType = resourceType;
  const resolvedResourceId = resourceId ?? dashboardId;
  const { t } = useTranslation();
  const {
    listSubscriptions,
    createSubscription,
    updateSubscription,
    deleteSubscription,
    executeSubscription,
    getExecution,
  } = useDashboardSubscriptionApi();
  const { getChannelData } = useChannelApi();
  const getChannelDataRef = useRef(getChannelData);
  getChannelDataRef.current = getChannelData;
  const [form] = Form.useForm<SubscriptionFormValues>();
  const [subscriptions, setSubscriptions] = useState<
    DashboardSubscription[]
  >([]);
  const [emailChannels, setEmailChannels] = useState<EmailChannelOption[]>(
    [],
  );
  const [editing, setEditing] = useState<DashboardSubscription | null>(null);
  const [formVisible, setFormVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [channelsLoading, setChannelsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [executingId, setExecutingId] = useState<number | null>(null);
  const [updatingSnapshotId, setUpdatingSnapshotId] = useState<number | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [executionResult, setExecutionResult] =
    useState<DashboardExecutionCreated | null>(null);

  const loadSubscriptions = useCallback(
    async (options?: { silent?: boolean }) => {
      if (!options?.silent) setLoading(true);
      setError(null);
      setLoadFailed(false);
      try {
        setSubscriptions(
          await listSubscriptions({
            resourceType: resolvedResourceType,
            resourceId: resolvedResourceId!,
          }),
        );
      } catch {
        setError(t('dashboard.subscriptionLoadFailed'));
        setLoadFailed(true);
      } finally {
        if (!options?.silent) setLoading(false);
      }
    },
    [listSubscriptions, resolvedResourceId, resolvedResourceType, t],
  );

  useEffect(() => {
    if (!open) return;
    setExecutionResult(null);
    void loadSubscriptions();
  }, [loadSubscriptions, open]);

  useEffect(() => {
    if (!open || !executionResult || !isInFlightExecutionStatus(executionResult.status)) {
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const execution = await getExecution(executionResult.execution_id);
        if (cancelled) return;
        setExecutionResult((current) => current ? {
          ...current,
          status: execution.status,
        } : current);
        await loadSubscriptions({ silent: true });
        if (!cancelled && isInFlightExecutionStatus(execution.status)) {
          timer = setTimeout(poll, 2000);
        }
      } catch {
        if (!cancelled) {
          setError(t('dashboard.subscriptionExecutionQueryFailed'));
          timer = setTimeout(poll, 2000);
        }
      }
    };

    timer = setTimeout(poll, 2000);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [executionResult, getExecution, loadSubscriptions, open, t]);

  useEffect(() => {
    if (!open || !subscriptions.some(hasInFlightSubscriptionExecution)) {
      return;
    }
    const timer = setInterval(() => {
      void loadSubscriptions({ silent: true });
    }, 2000);
    return () => clearInterval(timer);
  }, [loadSubscriptions, open, subscriptions]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setChannelsLoading(true);
    (async () => {
      try {
        const response = await getChannelDataRef.current({
          channel_type: 'email',
          page: 1,
          page_size: 100,
        });
        if (cancelled) return;
        setEmailChannels(normalizeChannelList(response));
      } catch {
        if (cancelled) return;
        setEmailChannels([]);
        setError(t('dashboard.subscriptionChannelLoadFailed'));
      } finally {
        if (!cancelled) setChannelsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, t]);

  const channelOptions = useMemo(() => {
    const options = emailChannels.map((channel) => ({
      value: channel.id,
      label: channel.name,
    }));
    if (
      editing?.email_channel
      && !options.some((option) => option.value === editing.email_channel)
    ) {
      options.unshift({
        value: editing.email_channel,
        label: String(editing.email_channel),
      });
    }
    return options;
  }, [editing, emailChannels]);

  const openCreateForm = () => {
    setEditing(null);
    setError(null);
    setLoadFailed(false);
    form.setFieldsValue({
      name: '',
      recipient_email: '',
      email_channel: undefined,
      status: 'active',
      schedule_type: null,
      schedule_hour: 9,
      schedule_minute: 0,
      schedule_weekday: 0,
      schedule_day_of_month: 1,
      timezone: 'Asia/Shanghai',
    });
    setFormVisible(true);
  };

  const openEditForm = (subscription: DashboardSubscription) => {
    setEditing(subscription);
    setError(null);
    setLoadFailed(false);
    form.setFieldsValue({
      name: subscription.name,
      recipient_email: subscription.recipient_email,
      email_channel: subscription.email_channel,
      status: subscription.status,
      schedule_type: subscription.schedule_type,
      schedule_hour: subscription.schedule_hour ?? 9,
      schedule_minute: subscription.schedule_minute ?? 0,
      schedule_weekday: subscription.schedule_weekday ?? 0,
      schedule_day_of_month: subscription.schedule_day_of_month ?? 1,
      timezone: subscription.timezone ?? 'Asia/Shanghai',
    });
    setFormVisible(true);
  };

  const submit = async (values: SubscriptionFormValues) => {
    if (values.email_channel == null) {
      setError(t('dashboard.subscriptionChannelRequired'));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const hasSchedule = Boolean(values.schedule_type);
      const payload = {
        name: values.name,
        recipient_email: values.recipient_email,
        email_channel: values.email_channel,
        status: values.status ?? 'active',
        schedule_type: hasSchedule ? values.schedule_type : null,
        schedule_hour: hasSchedule ? values.schedule_hour ?? null : null,
        schedule_minute: hasSchedule ? values.schedule_minute ?? null : null,
        schedule_weekday:
          hasSchedule && values.schedule_type === 'weekly'
            ? values.schedule_weekday ?? null
            : null,
        schedule_day_of_month:
          hasSchedule && values.schedule_type === 'monthly'
            ? values.schedule_day_of_month ?? null
            : null,
        timezone: hasSchedule ? values.timezone ?? null : null,
        ...(editing
          ? { version: editing.version, revision: editing.revision }
          : {}),
      };
      if (editing) {
        await updateSubscription(editing.id, payload);
      } else if (resolvedResourceType === 'screen') {
        await createSubscription({
          resource_type: 'screen',
          resource_id: resolvedResourceId!,
          applied_filter_values: appliedFilterValues,
          ...payload,
        });
      } else {
        await createSubscription({
          dashboard: resolvedResourceId!,
          applied_filter_values: appliedFilterValues,
          ...payload,
        });
      }
      setFormVisible(false);
      setEditing(null);
      form.resetFields();
      await loadSubscriptions();
    } catch {
      setError(
        t(
          editing
            ? 'dashboard.subscriptionUpdateFailed'
            : 'dashboard.subscriptionCreateFailed',
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  const remove = async (subscription: DashboardSubscription) => {
    setDeletingId(subscription.id);
    setError(null);
    setLoadFailed(false);
    try {
      await deleteSubscription(subscription.id, subscription.revision);
      await loadSubscriptions();
    } catch {
      setError(t('dashboard.subscriptionDeleteFailed'));
    } finally {
      setDeletingId(null);
    }
  };

  const updateSnapshot = async (subscription: DashboardSubscription) => {
    setUpdatingSnapshotId(subscription.id);
    setError(null);
    setLoadFailed(false);
    try {
      await updateSubscription(subscription.id, {
        applied_filter_values: appliedFilterValues,
        version: subscription.version,
        revision: subscription.revision,
      });
      await loadSubscriptions();
      message.success(t('dashboard.subscriptionSnapshotUpdateSuccess'));
    } catch {
      setError(t('dashboard.subscriptionSnapshotUpdateFailed'));
    } finally {
      setUpdatingSnapshotId(null);
    }
  };

  const executeManualTest = async (id: number) => {
    setExecutingId(id);
    setError(null);
    setLoadFailed(false);
    setExecutionResult(null);
    try {
      const result = await executeSubscription(id, crypto.randomUUID());
      setExecutionResult(result);
      await loadSubscriptions({ silent: true });
    } catch {
      setError(t('dashboard.subscriptionExecuteFailed'));
    } finally {
      setExecutingId(null);
    }
  };

  const executionStatusLabel = (status: DashboardExecutionStatus) =>
    t(`dashboard.executionStatus${status[0].toUpperCase()}${status.slice(1)}`);

  const executionStatusColor = (
    status: DashboardExecutionStatus,
  ): string => {
    if (status === 'succeeded') return 'success';
    if (status === 'failed') return 'error';
    if (status === 'unknown') return 'warning';
    if (status === 'running') return 'processing';
    return 'default';
  };

  const renderExecutionSummary = (
    summary: DashboardExecutionSummary | null,
    kind: 'scheduled' | 'manual_test',
  ) => {
    if (!summary) {
      return '-';
    }
    const timeLabel =
      kind === 'scheduled'
        ? t('dashboard.subscriptionExecutionScheduledAt')
        : t('dashboard.subscriptionExecutionTestedAt');
    const timeValue =
      kind === 'scheduled'
        ? summary.scheduled_time_utc ?? summary.created_at
        : summary.created_at;
    const detail = (
      <Space direction="vertical" size={2} className="max-w-80 text-xs">
        <span className="block text-white/90">
          {timeLabel}
          {': '}
          {timeValue}
        </span>
        {summary.finished_at ? (
          <span className="block text-white/90">
            {t('dashboard.subscriptionExecutionFinishedAt')}
            {': '}
            {summary.finished_at}
          </span>
        ) : null}
        {summary.status === 'failed' && summary.error_message ? (
          <span className="block text-red-200">
            {t('dashboard.subscriptionExecutionFailureReason')}
            {': '}
            {summary.error_message}
          </span>
        ) : null}
      </Space>
    );
    return (
      <Tooltip title={detail} placement="topLeft">
        <Tag color={executionStatusColor(summary.status)} className="cursor-help">
          {executionStatusLabel(summary.status)}
        </Tag>
      </Tooltip>
    );
  };

  const channelNameById = useMemo(() => {
    return new Map(emailChannels.map((channel) => [channel.id, channel.name]));
  }, [emailChannels]);

  const columns: TableColumnsType<DashboardSubscription> = [
    {
      title: t('dashboard.subscriptionName'),
      dataIndex: 'name',
      width: 150,
      ellipsis: { showTitle: false },
      render: (name: string) => <Tooltip title={name}>{name}</Tooltip>,
    },
    {
      title: t('dashboard.subscriptionStatus'),
      dataIndex: 'status',
      width: 90,
      render: (status: DashboardSubscriptionStatus) => (
        <Tag color={status === 'active' ? 'success' : 'default'}>
          {t(status === 'active' ? 'dashboard.subscriptionStatusActive' : 'dashboard.subscriptionStatusPaused')}
        </Tag>
      ),
    },
    {
      title: t('dashboard.subscriptionEmail'),
      dataIndex: 'recipient_email',
      width: 190,
      ellipsis: { showTitle: false },
      render: (email: string) => <Tooltip title={email}>{email}</Tooltip>,
    },
    {
      title: t('dashboard.subscriptionChannel'),
      dataIndex: 'email_channel',
      width: 130,
      ellipsis: { showTitle: false },
      render: (channelId: number) => {
        const name = channelNameById.get(channelId) ?? String(channelId);
        return <Tooltip title={name}>{name}</Tooltip>;
      },
    },
    {
      title: t('dashboard.subscriptionScheduleType'),
      width: 150,
      render: (_, subscription) => formatSubscriptionScheduleSummary(subscription, t) ?? '-',
    },
    {
      title: t('dashboard.subscriptionLatestScheduled'),
      width: 120,
      render: (_, subscription) => (
        <span data-testid={`latest-scheduled-${subscription.id}`}>
          {renderExecutionSummary(subscription.latest_scheduled_execution, 'scheduled')}
        </span>
      ),
    },
    {
      title: t('dashboard.subscriptionLatestManualTest'),
      width: 120,
      render: (_, subscription) => (
        <span data-testid={`latest-manual-test-${subscription.id}`}>
          {renderExecutionSummary(subscription.latest_manual_test_execution, 'manual_test')}
        </span>
      ),
    },
    {
      title: t('common.actions'),
      fixed: 'right',
      width: 260,
      render: (_, subscription) => (
        <Space size={0}>
          <Button
            type="link"
            size="small"
            loading={executingId === subscription.id}
            disabled={hasInFlightSubscriptionExecution(subscription) || (executingId !== null && executingId !== subscription.id)}
            onClick={() => void executeManualTest(subscription.id)}
          >
            {t('dashboard.subscriptionExecute')}
          </Button>
          <Popconfirm
            title={t('dashboard.subscriptionSnapshotUpdateConfirm')}
            onConfirm={() => updateSnapshot(subscription)}
          >
            <Button
              type="link"
              size="small"
              loading={updatingSnapshotId === subscription.id}
              disabled={
                updatingSnapshotId !== null
                && updatingSnapshotId !== subscription.id
              }
            >
              {t('dashboard.subscriptionSnapshotUpdate')}
            </Button>
          </Popconfirm>
          <Button type="link" size="small" onClick={() => openEditForm(subscription)}>
            {t('common.edit')}
          </Button>
          <Popconfirm title={t('dashboard.subscriptionDeleteConfirm')} onConfirm={() => remove(subscription)}>
            <Button type="link" size="small" danger loading={deletingId === subscription.id} disabled={deletingId !== null && deletingId !== subscription.id}>
              {t('common.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Drawer
      open={open}
      title={t('dashboard.subscriptionTitle')}
      onClose={onClose}
      width={830}
      destroyOnHidden
    >
      {error && (
        <Alert
          className="mb-4"
          type="error"
          showIcon
          message={error}
          action={
            loadFailed ? (
              <Button
                size="small"
                loading={loading}
                onClick={() => void loadSubscriptions()}
              >
                {t('common.retry')}
              </Button>
            ) : undefined
          }
        />
      )}

      {formVisible ? (
        <Form<SubscriptionFormValues>
          form={form}
          layout="vertical"
          onFinish={submit}
          initialValues={{ status: 'active' }}
        >
          <Form.Item
            label={t('dashboard.subscriptionName')}
            name="name"
            rules={[
              {
                required: true,
                message: t('dashboard.subscriptionNameRequired'),
              },
            ]}
          >
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item
            label={t('dashboard.subscriptionEmail')}
            name="recipient_email"
            rules={[
              {
                required: true,
                message: t('dashboard.subscriptionEmailRequired'),
              },
              {
                type: 'email',
                message: t('dashboard.subscriptionEmailInvalid'),
              },
            ]}
          >
            <Input type="email" />
          </Form.Item>
          <Form.Item
            label={t('dashboard.subscriptionChannel')}
            name="email_channel"
            rules={[
              {
                required: true,
                message: t('dashboard.subscriptionChannelRequired'),
              },
            ]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              loading={channelsLoading}
              placeholder={t('dashboard.subscriptionChannelPlaceholder')}
              options={channelOptions}
            />
          </Form.Item>
          <Form.Item
            label={t('dashboard.subscriptionScheduleType')}
            name="schedule_type"
          >
            <Select
              allowClear
              placeholder={t('dashboard.subscriptionScheduleNone')}
              options={[
                {
                  value: 'daily',
                  label: t('dashboard.subscriptionScheduleDaily'),
                },
                {
                  value: 'weekly',
                  label: t('dashboard.subscriptionScheduleWeekly'),
                },
                {
                  value: 'monthly',
                  label: t('dashboard.subscriptionScheduleMonthly'),
                },
              ]}
            />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prev, next) =>
              prev.schedule_type !== next.schedule_type
            }
          >
            {({ getFieldValue }) => {
              const scheduleType = getFieldValue(
                'schedule_type',
              ) as DashboardScheduleType | null;
              if (!scheduleType) {
                return null;
              }
              return (
                <>
                  <Form.Item
                    label={t('dashboard.subscriptionTimezone')}
                    name="timezone"
                    rules={[
                      {
                        required: true,
                        message: t('dashboard.subscriptionTimezoneRequired'),
                      },
                    ]}
                  >
                    <Select
                      showSearch
                      options={[
                        { value: 'Asia/Shanghai', label: 'Asia/Shanghai' },
                        {
                          value: 'America/New_York',
                          label: 'America/New_York',
                        },
                        { value: 'UTC', label: 'UTC' },
                      ]}
                    />
                  </Form.Item>
                  <Space className="w-full" size="middle">
                    <Form.Item
                      label={t('dashboard.subscriptionScheduleHour')}
                      name="schedule_hour"
                      rules={[{ required: true }]}
                      className="flex-1"
                    >
                      <Select
                        options={Array.from({ length: 24 }, (_, hour) => ({
                          value: hour,
                          label: String(hour).padStart(2, '0'),
                        }))}
                      />
                    </Form.Item>
                    <Form.Item
                      label={t('dashboard.subscriptionScheduleMinute')}
                      name="schedule_minute"
                      rules={[{ required: true }]}
                      className="flex-1"
                    >
                      <Select
                        options={Array.from({ length: 60 }, (_, minute) => ({
                          value: minute,
                          label: String(minute).padStart(2, '0'),
                        }))}
                      />
                    </Form.Item>
                  </Space>
                  {scheduleType === 'weekly' ? (
                    <Form.Item
                      label={t('dashboard.subscriptionScheduleWeekday')}
                      name="schedule_weekday"
                      rules={[{ required: true }]}
                    >
                      <Select
                        options={[
                          {
                            value: 0,
                            label: t('dashboard.subscriptionWeekdayMon'),
                          },
                          {
                            value: 1,
                            label: t('dashboard.subscriptionWeekdayTue'),
                          },
                          {
                            value: 2,
                            label: t('dashboard.subscriptionWeekdayWed'),
                          },
                          {
                            value: 3,
                            label: t('dashboard.subscriptionWeekdayThu'),
                          },
                          {
                            value: 4,
                            label: t('dashboard.subscriptionWeekdayFri'),
                          },
                          {
                            value: 5,
                            label: t('dashboard.subscriptionWeekdaySat'),
                          },
                          {
                            value: 6,
                            label: t('dashboard.subscriptionWeekdaySun'),
                          },
                        ]}
                      />
                    </Form.Item>
                  ) : null}
                  {scheduleType === 'monthly' ? (
                    <Form.Item
                      label={t('dashboard.subscriptionScheduleDayOfMonth')}
                      name="schedule_day_of_month"
                      rules={[{ required: true }]}
                    >
                      <Select
                        options={Array.from({ length: 31 }, (_, index) => ({
                          value: index + 1,
                          label: String(index + 1),
                        }))}
                      />
                    </Form.Item>
                  ) : null}
                </>
              );
            }}
          </Form.Item>
          {editing && (
            <Form.Item
              label={t('dashboard.subscriptionStatus')}
              name="status"
            >
              <Select
                options={[
                  {
                    value: 'active',
                    label: t('dashboard.subscriptionStatusActive'),
                  },
                  {
                    value: 'paused',
                    label: t('dashboard.subscriptionStatusPaused'),
                  },
                ]}
              />
            </Form.Item>
          )}
          <Space className="flex justify-end">
            <Button
              onClick={() => {
                setFormVisible(false);
                setEditing(null);
                setError(null);
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button type="primary" htmlType="submit" loading={saving}>
              {t('dashboard.subscriptionSave')}
            </Button>
          </Space>
        </Form>
      ) : (
        <>
          <div className="mb-4 flex justify-end">
            <Button
              type="primary"
              icon={<PlusOutlined aria-hidden="true" />}
              onClick={openCreateForm}
            >
              {t('dashboard.subscriptionCreate')}
            </Button>
          </div>
          <Spin spinning={loading}>
            <Table
              rowKey="id"
              columns={columns}
              dataSource={subscriptions}
              pagination={false}
              scroll={{ x: 1210 }}
              locale={{
                emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('dashboard.subscriptionEmpty')} />,
              }}
            />
          </Spin>
        </>
      )}
    </Drawer>
  );
};

export default DashboardSubscriptionModal;
