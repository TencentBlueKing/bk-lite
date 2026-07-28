'use client';

import { useCallback, useEffect, useState } from 'react';
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
  DashboardSubscription,
  DashboardSubscriptionStatus,
} from '@/app/ops-analysis/types/dashboardSubscription';
import { useTranslation } from '@/utils/i18n';

interface DashboardSubscriptionModalProps {
  open: boolean;
  dashboardId: number;
  onClose: () => void;
}

interface SubscriptionFormValues {
  name: string;
  recipient_email: string;
  status: DashboardSubscriptionStatus;
}

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
  } = useDashboardSubscriptionApi();
  const [form] = Form.useForm<SubscriptionFormValues>();
  const [subscriptions, setSubscriptions] = useState<
    DashboardSubscription[]
  >([]);
  const [editing, setEditing] = useState<DashboardSubscription | null>(null);
  const [formVisible, setFormVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  const loadSubscriptions = useCallback(async () => {
    setLoading(true);
    setError(null);
    setLoadFailed(false);
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
    if (open) {
      void loadSubscriptions();
    }
  }, [loadSubscriptions, open]);

  const openCreateForm = () => {
    setEditing(null);
    setError(null);
    setLoadFailed(false);
    form.setFieldsValue({
      name: '',
      recipient_email: '',
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
      status: subscription.status,
    });
    setFormVisible(true);
  };

  const submit = async (values: SubscriptionFormValues) => {
    setSaving(true);
    setError(null);
    try {
      if (editing) {
        await updateSubscription(editing.id, values);
      } else {
        await createSubscription({
          dashboard: dashboardId,
          ...values,
          status: values.status ?? 'active',
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
                      <Typography.Text
                        type="secondary"
                        ellipsis={{ tooltip: subscription.recipient_email }}
                        className="block max-w-96"
                      >
                        {subscription.recipient_email}
                      </Typography.Text>
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
