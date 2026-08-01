'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
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
  dashboardId: number;
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
  appliedFilterValues = {},
  onClose,
}: DashboardSubscriptionModalProps) => {
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
  const [queryingExecution, setQueryingExecution] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [executionNotice, setExecutionNotice] = useState<string | null>(
    null,
  );
  const [executionResult, setExecutionResult] =
    useState<DashboardExecutionCreated | null>(null);

  const loadSubscriptions = useCallback(
    async (options?: { preserveExecutionNotice?: boolean }) => {
      setLoading(true);
      setError(null);
      setLoadFailed(false);
      if (!options?.preserveExecutionNotice) {
        setExecutionNotice(null);
        setExecutionResult(null);
      }
      try {
        setSubscriptions(await listSubscriptions(dashboardId));
      } catch {
        setError(t('dashboard.subscriptionLoadFailed'));
        setLoadFailed(true);
      } finally {
        setLoading(false);
      }
    },
    [dashboardId, listSubscriptions, t],
  );

  useEffect(() => {
    if (!open) return;
    void loadSubscriptions();
  }, [loadSubscriptions, open]);

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
        applied_filter_values: appliedFilterValues,
        ...(editing ? { version: editing.version } : {}),
      };
      if (editing) {
        await updateSubscription(editing.id, payload);
      } else {
        await createSubscription({
          dashboard: dashboardId,
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

  const remove = async (id: number) => {
    setDeletingId(id);
    setError(null);
    setLoadFailed(false);
    try {
      await deleteSubscription(id);
      await loadSubscriptions();
    } catch {
      setError(t('dashboard.subscriptionDeleteFailed'));
    } finally {
      setDeletingId(null);
    }
  };

  const executeManualTest = async (id: number) => {
    setExecutingId(id);
    setError(null);
    setLoadFailed(false);
    setExecutionNotice(null);
    setExecutionResult(null);
    try {
      const result = await executeSubscription(id, crypto.randomUUID());
      setExecutionResult(result);
      setExecutionNotice(t('dashboard.subscriptionExecuteCreated'));
      await loadSubscriptions({ preserveExecutionNotice: true });
    } catch {
      setError(t('dashboard.subscriptionExecuteFailed'));
    } finally {
      setExecutingId(null);
    }
  };

  const refreshExecutionStatus = async () => {
    if (!executionResult) return;
    setQueryingExecution(true);
    setError(null);
    try {
      const execution = await getExecution(executionResult.execution_id);
      setExecutionResult({
        execution_id: execution.id,
        status: execution.status,
        request_id: executionResult.request_id,
        created: executionResult.created,
      });
      await loadSubscriptions({ preserveExecutionNotice: true });
    } catch {
      setError(t('dashboard.subscriptionExecutionQueryFailed'));
    } finally {
      setQueryingExecution(false);
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
      return (
        <Typography.Text type="secondary" className="block text-xs">
          {t('dashboard.subscriptionExecutionEmpty')}
        </Typography.Text>
      );
    }
    const timeLabel =
      kind === 'scheduled'
        ? t('dashboard.subscriptionExecutionScheduledAt')
        : t('dashboard.subscriptionExecutionTestedAt');
    const timeValue =
      kind === 'scheduled'
        ? summary.scheduled_time_utc ?? summary.created_at
        : summary.created_at;
    return (
      <Space direction="vertical" size={0} className="w-full">
        <Space size={4} wrap>
          <Tag color={executionStatusColor(summary.status)}>
            {executionStatusLabel(summary.status)}
          </Tag>
        </Space>
        <Typography.Text type="secondary" className="block text-xs">
          {timeLabel}
          {': '}
          {timeValue}
        </Typography.Text>
        {summary.finished_at ? (
          <Typography.Text type="secondary" className="block text-xs">
            {t('dashboard.subscriptionExecutionFinishedAt')}
            {': '}
            {summary.finished_at}
          </Typography.Text>
        ) : null}
        {summary.status === 'failed' && summary.error_message ? (
          <Typography.Text type="danger" className="block text-xs">
            {t('dashboard.subscriptionExecutionFailureReason')}
            {': '}
            {summary.error_message}
          </Typography.Text>
        ) : null}
      </Space>
    );
  };

  const executionAlertType = (
    status: DashboardExecutionStatus,
  ): 'success' | 'info' | 'warning' | 'error' => {
    if (status === 'succeeded') return 'success';
    if (status === 'failed') return 'error';
    if (status === 'unknown') return 'warning';
    return 'info';
  };

  const channelNameById = useMemo(() => {
    return new Map(emailChannels.map((channel) => [channel.id, channel.name]));
  }, [emailChannels]);

  return (
    <Modal
      open={open}
      title={t('dashboard.subscriptionTitle')}
      footer={null}
      onCancel={onClose}
      width={720}
      styles={{
        body: {
          maxHeight: 'calc(100vh - 240px)',
          overflowY: 'auto',
        },
      }}
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
      {executionNotice && (
        <Alert
          className="mb-4"
          type={
            executionResult
              ? executionAlertType(executionResult.status)
              : 'info'
          }
          showIcon
          message={
            executionResult
              ? `${executionNotice} · ${t('dashboard.subscriptionExecutionStatus')}：${executionStatusLabel(executionResult.status)}`
              : executionNotice
          }
          action={
            executionResult ? (
              <Button
                size="small"
                loading={queryingExecution}
                onClick={() => void refreshExecutionStatus()}
              >
                {t('dashboard.subscriptionExecutionRefresh')}
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
            <List
              dataSource={subscriptions}
              locale={{
                emptyText: (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('dashboard.subscriptionEmpty')}
                  />
                ),
              }}
              renderItem={(subscription) => (
                <List.Item
                  actions={[
                    <Button
                      key="execute"
                      type="link"
                      size="small"
                      loading={executingId === subscription.id}
                      disabled={
                        hasInFlightSubscriptionExecution(subscription)
                        || (
                          executingId !== null
                          && executingId !== subscription.id
                        )
                      }
                      onClick={() => executeManualTest(subscription.id)}
                    >
                      {t('dashboard.subscriptionExecute')}
                    </Button>,
                    <Button
                      key="edit"
                      type="link"
                      size="small"
                      onClick={() => openEditForm(subscription)}
                    >
                      {t('common.edit')}
                    </Button>,
                    <Popconfirm
                      key="delete"
                      title={t('dashboard.subscriptionDeleteConfirm')}
                      onConfirm={() => remove(subscription.id)}
                    >
                      <Button
                        type="link"
                        size="small"
                        danger
                        loading={deletingId === subscription.id}
                        disabled={
                          deletingId !== null
                          && deletingId !== subscription.id
                        }
                      >
                        {t('common.delete')}
                      </Button>
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <Typography.Text
                          ellipsis={{ tooltip: subscription.name }}
                          className="max-w-64"
                        >
                          {subscription.name}
                        </Typography.Text>
                        <Tag
                          color={
                            subscription.status === 'active'
                              ? 'success'
                              : 'default'
                          }
                        >
                          {t(
                            subscription.status === 'active'
                              ? 'dashboard.subscriptionStatusActive'
                              : 'dashboard.subscriptionStatusPaused',
                          )}
                        </Tag>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={4} className="w-full">
                        <Typography.Text
                          type="secondary"
                          ellipsis={{ tooltip: subscription.recipient_email }}
                          className="block max-w-96"
                        >
                          {subscription.recipient_email}
                        </Typography.Text>
                        <Typography.Text
                          type="secondary"
                          ellipsis={{
                            tooltip:
                              channelNameById.get(subscription.email_channel)
                              ?? String(subscription.email_channel),
                          }}
                          className="block max-w-96"
                        >
                          {t('dashboard.subscriptionChannel')}：
                          {channelNameById.get(subscription.email_channel)
                            ?? subscription.email_channel}
                        </Typography.Text>
                        <Typography.Text type="secondary" className="block">
                          {t('dashboard.subscriptionNextRunAt')}
                          {': '}
                          {subscription.next_run_at
                            ?? t('dashboard.subscriptionScheduleNone')}
                        </Typography.Text>
                        <Typography.Text
                          type="secondary"
                          className="block"
                          data-testid={`schedule-summary-${subscription.id}`}
                        >
                          {t('dashboard.subscriptionScheduleType')}
                          {': '}
                          {formatSubscriptionScheduleSummary(
                            subscription,
                            t,
                          )
                            ?? t('dashboard.subscriptionScheduleNone')}
                        </Typography.Text>
                        <Typography.Text
                          type="secondary"
                          className="block"
                          data-testid={`schedule-timezone-${subscription.id}`}
                        >
                          {t('dashboard.subscriptionTimezone')}
                          {': '}
                          {subscription.timezone
                            ?? t('dashboard.subscriptionScheduleNone')}
                        </Typography.Text>
                        <div
                          data-testid={`latest-scheduled-${subscription.id}`}
                          className="rounded border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-2 py-1"
                        >
                          <Typography.Text className="mb-1 block text-xs font-medium">
                            {t('dashboard.subscriptionLatestScheduled')}
                          </Typography.Text>
                          {renderExecutionSummary(
                            subscription.latest_scheduled_execution,
                            'scheduled',
                          )}
                        </div>
                        <div
                          data-testid={`latest-manual-test-${subscription.id}`}
                          className="rounded border border-[var(--color-border-2)] bg-[var(--color-fill-1)] px-2 py-1"
                        >
                          <Typography.Text className="mb-1 block text-xs font-medium">
                            {t('dashboard.subscriptionLatestManualTest')}
                          </Typography.Text>
                          {renderExecutionSummary(
                            subscription.latest_manual_test_execution,
                            'manual_test',
                          )}
                        </div>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Spin>
        </>
      )}
    </Modal>
  );
};

export default DashboardSubscriptionModal;
