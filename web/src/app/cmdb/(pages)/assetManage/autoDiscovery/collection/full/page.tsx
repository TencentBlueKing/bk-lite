'use client';

import React from 'react';
import { Input, Button, Table, Tag } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

const fullData = [
  {
    key: '1',
    name: '资源采集 - 全面',
    status: '正常',
    summary: [
      { count: 1, type: '新增资产', color: 'success' },
      { count: 0, type: '更新资产', color: 'processing' },
      { count: 0, type: '新增关联', color: 'warning' },
      { count: 2, type: '下线资产', color: 'error' },
    ],
    creator: 'superadmin',
    executeTime: '2025-01-10 12:30:00',
  },
];

const FullCollection: React.FC = () => {
  const { t } = useTranslation();
  const fullColumns = [
    { title: t('Collection.taskName'), dataIndex: 'name', key: 'name' },
    {
      title: t('Collection.executeStatus'),
      dataIndex: 'status',
      key: 'status',
      render: (text: string) => <Tag color="processing">{text}</Tag>,
    },
    {
      title: t('Collection.collectSummary'),
      dataIndex: 'summary',
      key: 'summary',
      render: (summaries: { count: number; type: string; color: string }[]) => (
        <div className="flex gap-2">
          {summaries.map((item, index) => (
            <Tag key={index} color={item.color}>
              {item.type}: {item.count}
            </Tag>
          ))}
        </div>
      ),
    },
    { title: t('Collection.creator'), dataIndex: 'creator', key: 'creator' },
    { title: t('Collection.executeTime'), dataIndex: 'executeTime', key: 'executeTime' },
    {
      title: t('common.actions'),
      key: 'action',
      render: () => (
        <div className="flex gap-3">
          <Button type="link" size="small">
            {t('common.detail')}
          </Button>
          <Button type="link" size="small">
            {t('Collection.executeNow')}
          </Button>
          <Button type="link" size="small">
            {t('common.edit')}
          </Button>
          <Button type="link" size="small">
            {t('common.delete')}
          </Button>
        </div>
      ),
    },
  ];
  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex-1 p-6 flex flex-col overflow-hidden">
        <div className="mb-4 flex justify-between items-center flex-shrink-0">
          <Input
            placeholder={t('Collection.inputTaskPlaceholder')}
            prefix={<SearchOutlined className="text-gray-400" />}
            className="max-w-md"
          />
          <Button type="primary" className="!rounded-button whitespace-nowrap">
            {t('Collection.addTaskTitle')}
          </Button>
        </div>
        <div className="rounded-lg shadow-sm flex-1 overflow-auto">
          <Table
            columns={fullColumns}
            dataSource={fullData}
            pagination={{
              total: fullData.length,
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => t('Collection.taskDetail.paginationTotal', '', { total }),
            }}
          />
        </div>
      </div>
    </div>
  );
};

export default FullCollection;
