'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { BuildRecord } from '@/app/opspilot/types/wiki';

const STATUS_COLOR: Record<string, string> = {
  success: 'green',
  running: 'blue',
  partial: 'gold',
  failed: 'red',
};

const BuildRecordTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchBuildRecords } = useWikiApi();
  const [data, setData] = useState<BuildRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchBuildRecords(kbId));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const columns: ColumnsType<BuildRecord> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 80 },
    { title: 'Trigger', dataIndex: 'trigger', key: 'trigger', width: 140 },
    {
      title: t('wiki.status'),
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    { title: 'Stage', dataIndex: 'stage', key: 'stage', width: 120 },
    {
      title: 'Counts',
      dataIndex: 'counts',
      key: 'counts',
      render: (c: Record<string, number>) => <span className="text-xs">{JSON.stringify(c || {})}</span>,
    },
    { title: 'Time', dataIndex: 'created_at', key: 'created_at', width: 180 },
  ];

  return <Table<BuildRecord> rowKey="id" loading={loading} columns={columns} dataSource={data} />;
};

export default BuildRecordTab;
