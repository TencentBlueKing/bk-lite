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
  DashboardSubscription,
  DashboardSubscriptionStatus,
} from '@/app/ops-analysis/types/dashboardSubscription';
import { useChannelApi } from '@/app/system-manager/api/channel';
import { useTranslation } from '@/utils/i18n';

interface DashboardSubscriptionModalProps {
  open: boolean;
  dashboardId: number;
  onClose: () => void;
}

interface SubscriptionFormValues {
  name: string;
  recipient_email: string;
  email_channel?: number;
  status: DashboardSubscriptionStatus;
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

const DashboardSubscriptionModal = ({
  open,
  dashboardId,
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

  const loadSubscriptions = useCallback(async () => {
    setLoading(true);
    setError(null);
    setLoadFailed(false);
    setExecutionNotice(null);
    setExecutionResult(null);
    try {
      setSubscriptions(await listSubscriptions(dashboardId));
    } catch {
      setError(t('dashboard.subscriptionLoadFailed'));
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [dashboardId, listSubscriptions, t]);

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
      const payload = {
        name: values.name,
        recipient_email: values.recipient_email,
        email_channel: values.email_channel,
        status: values.status ?? 'active',
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
      });
    } catch {
      setError(t('dashboard.subscriptionExecutionQueryFailed'));
    } finally {
      setQueryingExecution(false);
    }
  };

  const executionStatusLabel = (status: DashboardExecutionStatus) =>
    t(`dashboard.executionStatus${status[0].toUpperCase()}${status.slice(1)}`);

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
      width={640}
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
                        executingId !== null
                        && executingId !== subscription.id
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
                      <Space direction="vertical" size={0}>
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
