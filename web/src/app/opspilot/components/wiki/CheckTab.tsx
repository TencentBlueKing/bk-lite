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

// 检查类型本地化(spec 4.5)
const CHECK_TYPE_KEY: Record<string, string> = {
  conflict: 'wiki.checkConflict',
  duplicate: 'wiki.checkDuplicate',
  stale: 'wiki.checkStale',
  orphan: 'wiki.checkOrphan',
  broken_relation: 'wiki.checkBrokenRelation',
  no_source: 'wiki.checkNoSource',
  all_sources_invalid: 'wiki.checkAllSourcesInvalid',
  low_confidence: 'wiki.checkLowConfidence',
  cannot_merge: 'wiki.checkCannotMerge',
  schema_violation: 'wiki.checkSchemaViolation',
  missing: 'wiki.checkMissing',
  material_update: 'wiki.checkMaterialUpdate',
  source_invalid: 'wiki.checkSourceInvalid',
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
    {
      title: t('wiki.type'),
      dataIndex: 'check_type',
      key: 'check_type',
      width: 160,
      render: (ct: string) => (CHECK_TYPE_KEY[ct] ? t(CHECK_TYPE_KEY[ct]) : ct),
    },
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
      {/* scroll x:undefined 关闭 CustomTable 默认强制的横向滚动,列宽自适应容器,消除底部多余横向滚动条 */}
      <CustomTable<CheckItem>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={data}
        pagination={false}
        scroll={{ x: undefined }}
      />
    </div>
  );
};

export default CheckTab;
