'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Button, Descriptions, Drawer, Popconfirm, Space, Tag, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { BuildRecord } from '@/app/opspilot/types/wiki';

const STATUS_COLOR: Record<string, string> = {
  success: 'green',
  running: 'processing',
  partial: 'gold',
  failed: 'red',
  cancelled: 'default',
};

// 构建记录工作区(spec 4.4):长期记录 + 详情(输入版本/受影响页/错误)+ 重试/继续/取消/查看结果
const BuildRecordTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchBuildRecords, fetchBuildRecord, retryBuild, cancelBuild } = useWikiApi();
  const [data, setData] = useState<BuildRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<BuildRecord | null>(null);

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

  // 有 running 记录时每 3s 轮询刷新进度,全部结束自动停止
  useEffect(() => {
    if (!data.some((b) => b.status === 'running')) return;
    const timer = setInterval(() => load(), 3000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const openDetail = async (id: number) => setDetail(await fetchBuildRecord(id));
  const handleRetry = async (id: number) => {
    await retryBuild(id);
    message.success(t('wiki.saveSuccess'));
    load();
  };
  const handleCancel = async (id: number) => {
    await cancelBuild(id);
    message.success(t('wiki.saveSuccess'));
    load();
  };

  const columns: ColumnsType<BuildRecord> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    { title: t('wiki.trigger'), dataIndex: 'trigger', key: 'trigger', width: 120 },
    {
      title: t('wiki.status'),
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    { title: t('wiki.stage'), dataIndex: 'stage', key: 'stage', width: 120 },
    {
      title: t('wiki.counts'),
      dataIndex: 'counts',
      key: 'counts',
      render: (c: Record<string, number>) => <span className="text-xs">{JSON.stringify(c || {})}</span>,
    },
    { title: t('wiki.time'), dataIndex: 'created_at', key: 'created_at', width: 170 },
    {
      title: '',
      key: 'action',
      width: 180,
      render: (_: unknown, r) => (
        <Space>
          <Button type="link" size="small" onClick={() => openDetail(r.id)}>
            {t('wiki.viewResult')}
          </Button>
          {['failed', 'partial', 'cancelled'].includes(r.status) && (
            <Button type="link" size="small" onClick={() => handleRetry(r.id)}>
              {t('wiki.retry')}
            </Button>
          )}
          {r.status === 'running' && (
            <Popconfirm title={t('wiki.cancelConfirm')} onConfirm={() => handleCancel(r.id)}>
              <Button type="link" size="small" danger>
                {t('wiki.cancel')}
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <CustomTable<BuildRecord>
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={data}
        pagination={false}
        scroll={{ x: undefined }}
      />
      <Drawer
        title={`${t('wiki.buildRecord')} #${detail?.id ?? ''}`}
        open={!!detail}
        width={560}
        onClose={() => setDetail(null)}
      >
        {detail && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label={t('wiki.trigger')}>{detail.trigger}</Descriptions.Item>
            <Descriptions.Item label={t('wiki.operator')}>{detail.operator || '--'}</Descriptions.Item>
            <Descriptions.Item label={t('wiki.inputMaterial')}>{JSON.stringify(detail.inputs || {})}</Descriptions.Item>
            <Descriptions.Item label={t('wiki.stage')}>
              {detail.stage}({detail.progress ?? 0}%)
            </Descriptions.Item>
            <Descriptions.Item label={t('wiki.status')}>
              <Tag color={STATUS_COLOR[detail.status] || 'default'}>{detail.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('wiki.counts')}>{JSON.stringify(detail.counts || {})}</Descriptions.Item>
            <Descriptions.Item label={t('wiki.affectedPages')}>
              {(detail.affected_pages || []).join(', ') || '--'}
            </Descriptions.Item>
            <Descriptions.Item label={t('wiki.errors')}>{(detail.errors || []).join('; ') || '--'}</Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
};

export default BuildRecordTab;
