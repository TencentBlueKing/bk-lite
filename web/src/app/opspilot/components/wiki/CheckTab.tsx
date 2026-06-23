'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, Space, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { CheckItem } from '@/app/opspilot/types/wiki';

const STATUS_COLOR: Record<string, string> = {
  open: 'gold',
  resolved: 'green',
  dismissed: 'default',
};

const CheckTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchCheckItems, acceptCheck, rejectCheck, scan } = useWikiApi();
  const [data, setData] = useState<CheckItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchCheckItems(kbId));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const handleScan = async () => {
    setScanning(true);
    try {
      await scan(kbId);
      message.success(t('wiki.saveSuccess'));
      load();
    } finally {
      setScanning(false);
    }
  };

  const handleAccept = async (id: number) => {
    await acceptCheck(id);
    message.success(t('wiki.saveSuccess'));
    load();
  };

  const handleReject = async (id: number) => {
    await rejectCheck(id);
    message.success(t('wiki.saveSuccess'));
    load();
  };

  const columns: ColumnsType<CheckItem> = [
    { title: t('wiki.type'), dataIndex: 'check_type', key: 'check_type', width: 160 },
    {
      title: t('wiki.status'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    {
      title: t('wiki.related'),
      dataIndex: 'related',
      key: 'related',
      render: (r: Record<string, unknown>) => <span className="text-xs">{JSON.stringify(r || {})}</span>,
    },
    {
      title: '',
      key: 'action',
      width: 160,
      render: (_: unknown, record) =>
        record.status === 'open' ? (
          <Space>
            <Button type="link" size="small" onClick={() => handleAccept(record.id)}>
              {t('wiki.accept')}
            </Button>
            <Button type="link" size="small" danger onClick={() => handleReject(record.id)}>
              {t('wiki.reject')}
            </Button>
          </Space>
        ) : null,
    },
  ];

  return (
    <div>
      <div className="flex justify-end mb-3">
        <Button onClick={handleScan} loading={scanning}>
          {t('wiki.scan')}
        </Button>
      </div>
      <CustomTable<CheckItem>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={data}
        pagination={false}
        scroll={{ y: 'calc(100vh - 420px)' }}
      />
    </div>
  );
};

export default CheckTab;
