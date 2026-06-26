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

// 计数键 → 中文标签 + 配色(避免直接暴露 {"new":0,...} 这类 JSON,用户看不懂)
const COUNT_META: Record<string, { key: string; color: string }> = {
  new: { key: 'wiki.countNew', color: 'green' },
  updated: { key: 'wiki.countUpdated', color: 'blue' },
  unchanged: { key: 'wiki.countUnchanged', color: 'default' },
  pending_review: { key: 'wiki.countPendingReview', color: 'gold' },
};

// 触发/阶段/状态 → i18n key(避免界面直接显示 material / done / success 这类裸 key)
const TRIGGER_LABEL: Record<string, string> = {
  material: 'wiki.triggerMaterial',
  material_delete: 'wiki.triggerMaterialDelete',
  material_update: 'wiki.triggerMaterialUpdate',
  rebuild: 'wiki.triggerRebuild',
};
const STAGE_LABEL: Record<string, string> = {
  done: 'wiki.stageDone',
  failed: 'wiki.stageFailed',
  generating: 'wiki.stageGenerating',
  running: 'wiki.stageRunning',
  cancelled: 'wiki.stageCancelled',
};
const STATUS_LABEL: Record<string, string> = {
  success: 'wiki.buildSuccess',
  running: 'wiki.buildRunning',
  partial: 'wiki.buildPartial',
  failed: 'wiki.buildFailed',
  cancelled: 'wiki.buildCancelled',
};

// 构建记录工作区(spec 4.4):长期记录 + 详情(输入版本/受影响页/错误)+ 重试/继续/取消/查看结果
const BuildRecordTab: React.FC<{ kbId: number }> = ({ kbId }) => {
  const { t } = useTranslation();
  const { fetchBuildRecords, fetchBuildRecord, retryBuild, cancelBuild } = useWikiApi();
  const [data, setData] = useState<BuildRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<BuildRecord | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchBuildRecords(kbId, { page, page_size: pageSize });
      setData(res.items);
      setTotal(res.count);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, page, pageSize]);

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

  // 计数渲染:仅展示非零项为标签(新增 6 / 修改 3 …);全为 0 显示"无变更"
  const renderCounts = (c?: Record<string, number>) => {
    const entries = Object.entries(c || {}).filter(([, v]) => v);
    if (!entries.length) return <span className="text-[var(--color-text-4)]">{t('wiki.noChange')}</span>;
    return (
      <Space size={[4, 4]} wrap>
        {entries.map(([k, v]) => {
          const meta = COUNT_META[k];
          return (
            <Tag key={k} color={meta?.color || 'default'} className="m-0">
              {meta ? t(meta.key) : k} {v}
            </Tag>
          );
        })}
      </Space>
    );
  };

  const labelOf = (map: Record<string, string>, v: string) => (map[v] ? t(map[v]) : v || '--');

  const columns: ColumnsType<BuildRecord> = [
    {
      title: t('wiki.trigger'),
      dataIndex: 'trigger',
      key: 'trigger',
      width: 120,
      render: (v: string) => labelOf(TRIGGER_LABEL, v),
    },
    {
      title: t('wiki.status'),
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{labelOf(STATUS_LABEL, s)}</Tag>,
    },
    {
      title: t('wiki.stage'),
      dataIndex: 'stage',
      key: 'stage',
      width: 120,
      render: (v: string) => labelOf(STAGE_LABEL, v),
    },
    {
      title: t('wiki.counts'),
      dataIndex: 'counts',
      key: 'counts',
      render: (c: Record<string, number>) => renderCounts(c),
    },
    { title: t('wiki.time'), dataIndex: 'created_at', key: 'created_at', width: 170 },
    {
      title: t('common.actions'),
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
    // h-full + flex:给表格一个确定高度的父级,使 CustomTable 开启分页时自动算出的 scroll.y 稳定(否则只显示 1 行)
    <div className="h-full flex flex-col">
      <div className="flex-1 min-h-0">
        <CustomTable<BuildRecord>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={data}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
          scroll={{ x: undefined }}
        />
      </div>
      <Drawer
        title={`${t('wiki.buildRecord')} #${detail?.id ?? ''}`}
        open={!!detail}
        width={560}
        onClose={() => setDetail(null)}
      >
        {detail && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label={t('wiki.trigger')}>{labelOf(TRIGGER_LABEL, detail.trigger)}</Descriptions.Item>
            <Descriptions.Item label={t('wiki.operator')}>{detail.operator || '--'}</Descriptions.Item>
            <Descriptions.Item label={t('wiki.inputMaterial')}>{detail.input_label || '--'}</Descriptions.Item>
            <Descriptions.Item label={t('wiki.stage')}>
              {labelOf(STAGE_LABEL, detail.stage)}({detail.progress ?? 0}%)
            </Descriptions.Item>
            <Descriptions.Item label={t('wiki.status')}>
              <Tag color={STATUS_COLOR[detail.status] || 'default'}>{labelOf(STATUS_LABEL, detail.status)}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('wiki.counts')}>{renderCounts(detail.counts)}</Descriptions.Item>
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
