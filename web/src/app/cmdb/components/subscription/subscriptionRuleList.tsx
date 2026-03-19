import React from 'react';
import dayjs from 'dayjs';
import { Button, Popconfirm, Space, Switch, Table, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import { getOrganizationDisplayText } from '@/app/cmdb/utils/common';
import type { SubscriptionRule } from '@/app/cmdb/types/subscription';

interface SubscriptionRuleListProps {
  rules: SubscriptionRule[];
  loading: boolean;
  pagination: { current: number; pageSize: number; total: number };
  onPageChange: (page: number, pageSize: number) => void;
  onEdit: (rule: SubscriptionRule) => void;
  onDelete: (id: number) => void;
  onToggle: (id: number) => void;
  tableHeight?: string;
}

const SubscriptionRuleList: React.FC<SubscriptionRuleListProps> = ({
  rules,
  loading,
  pagination,
  onPageChange,
  onEdit,
  onDelete,
  onToggle,
  tableHeight = 'calc(100vh - 260px)',
}) => {
  const { t } = useTranslation();
  const { flatGroups } = useUserInfoContext();
  return (
    <Table<SubscriptionRule>
      rowKey="id"
      size="small"
      loading={loading}
      dataSource={rules}
      scroll={{ y: tableHeight }}
      pagination={{
        current: pagination.current,
        pageSize: pagination.pageSize,
        total: pagination.total,
        showSizeChanger: true,
        showTotal: (total) => `共 ${total} 条`,
        pageSizeOptions: [10, 20, 50, 100],
        onChange: onPageChange,
      }}
      columns={[
        {
          title: t('subscription.ruleName'),
          dataIndex: 'name',
          key: 'name',
          ellipsis: true,
          render: (_, record) => (
            <Tooltip title={record.name}>
              <Button
                type="link"
                style={{ paddingInline: 0, maxWidth: '100%' }}
                onClick={() => onEdit(record)}
              >
                <span className="truncate block">{record.name}</span>
              </Button>
            </Tooltip>
          ),
        },
        {
          title: t('subscription.organization'),
          dataIndex: 'organization',
          key: 'organization',
          width: 100,
          ellipsis: true,
          render: (value) => {
            const text = getOrganizationDisplayText(value, flatGroups);
            return (
              <Tooltip title={text}>
                <span>{text}</span>
              </Tooltip>
            );
          },
        },
        {
          title: t('subscription.targetModel'),
          dataIndex: 'model_id',
          key: 'model_id',
          width: 110,
          ellipsis: true,
        },
        {
          title: t('subscription.status'),
          dataIndex: 'is_enabled',
          key: 'is_enabled',
          width: 70,
          render: (_, record) => (
            <Tooltip
              title={
                record.is_enabled
                  ? t('subscription.enabled')
                  : t('subscription.disabled')
              }
            >
              <Switch
                size="small"
                checked={record.is_enabled}
                disabled={!record.can_manage}
                onChange={() => onToggle(record.id)}
              />
            </Tooltip>
          ),
        },
        {
          title: t('subscription.lastTriggeredAt'),
          dataIndex: 'last_triggered_at',
          key: 'last_triggered_at',
          width: 160,
          render: (v) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-'),
        },
        {
          title: t('common.actions'),
          key: 'actions',
          width: 110,
          render: (_, record) => {
            const editBtn = (
              <Button
                type="link"
                size="small"
                style={{ padding: 0 }}
                disabled={!record.can_manage}
                onClick={() => onEdit(record)}
              >
                {t('common.edit')}
              </Button>
            );
            const deleteBtn = (
              <Popconfirm
                title={t('subscription.deleteConfirm')}
                onConfirm={() => onDelete(record.id)}
                disabled={!record.can_manage}
              >
                <Button
                  type="link"
                  size="small"
                  style={{ padding: 0 }}
                  disabled={!record.can_manage}
                >
                  {t('common.delete')}
                </Button>
              </Popconfirm>
            );
            if (!record.can_manage) {
              return (
                <Space size={12}>
                  <Tooltip title={t('subscription.onlyOwnerCanManage')}>
                    {editBtn}
                  </Tooltip>
                  <Tooltip title={t('subscription.onlyOwnerCanManage')}>
                    {deleteBtn}
                  </Tooltip>
                </Space>
              );
            }
            return (
              <Space size={12}>
                {editBtn}
                {deleteBtn}
              </Space>
            );
          },
        },
      ]}
    />
  );
};

export default SubscriptionRuleList;
