'use client';

import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Tag, type TableColumnsType } from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import CustomTable from '@/components/custom-table';
import { useItsmApi } from '../api/useItsmApi';
import type { TicketExportRecord } from '../types';
import { ItsmDrawer } from './interaction-surfaces';
import { ItsmListToolbar } from './list-controls';

const STATUS = {
  pending: { label: '排队中', color: 'default' },
  running: { label: '生成中', color: 'processing' },
  done: { label: '已完成', color: 'success' },
  failed: { label: '失败', color: 'error' },
};

export function TicketExportHistory({ onClose }: { onClose: () => void }) {
  const { listTicketExports, retryTicketExport, downloadTicketExport } = useItsmApi();
  const { message } = App.useApp();
  const [rows, setRows] = useState<TicketExportRecord[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState({ current: 1, size: 20 });
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<number | null>(null);
  const actionLock = useRef(false);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    setLoading(true);
    const load = async () => {
      try {
        const result = await listTicketExports(page.current, page.size);
        if (!active) return;
        setRows(result.items);
        setCount(result.count);
        setError('');
        if (result.items.some(item => item.status === 'pending' || item.status === 'running')) {
          timer = setTimeout(() => void load(), 2500);
        }
      } catch {
        if (active) setError('加载导出记录失败，请刷新重试。');
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; clearTimeout(timer); };
  }, [listTicketExports, page, refresh]);

  const operate = async (item: TicketExportRecord) => {
    if (actionLock.current) return;
    actionLock.current = true;
    setBusy(item.id);
    try {
      if (item.status === 'failed') {
        await retryTicketExport(item.id);
        setPage(current => ({ ...current, current: 1 }));
        message.success('已重新提交导出任务');
        return;
      }
      const file = await downloadTicketExport(item.id);
      const url = URL.createObjectURL(file);
      const link = document.createElement('a');
      link.href = url;
      link.download = item.filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) {
      const fallback = item.status === 'failed' ? '无法重试，请重新筛选后导出。' : '无法下载，文件可能已过期或工单权限已变化。';
      message.error(item.status === 'failed' && failure instanceof Error ? failure.message : fallback);
    } finally {
      actionLock.current = false;
      setBusy(null);
    }
  };

  const columns: TableColumnsType<TicketExportRecord> = [
    { title: '提交时间', dataIndex: 'created_at', width: 150, className: 'tabular-nums', render: value => dayjs(value).format('YYYY-MM-DD HH:mm:ss') },
    { title: '状态', dataIndex: 'status', width: 85, render: (value: TicketExportRecord['status']) => <Tag color={STATUS[value].color}>{STATUS[value].label}</Tag> },
    { title: '工单数', dataIndex: 'count', width: 75, align: 'right', className: 'tabular-nums',
      render: (value, item) => item.status === 'done' ? value : '—' },
    { title: '文件或说明', render: (_, item) => <span className="break-all">
      {item.error || (item.status === 'done' ? item.downloadable ? item.filename : '文件已过期' : '—')}
    </span> },
    { title: '操作', width: 95, render: (_, item) => {
      if (item.status !== 'failed' && !item.downloadable) return '—';
      return <Button type="link" size="small" loading={busy === item.id} disabled={busy !== null && busy !== item.id}
        icon={item.downloadable ? <DownloadOutlined /> : undefined} onClick={() => void operate(item)}>
        {item.downloadable ? '下载' : '重试'}
      </Button>;
    } },
  ];

  return <ItsmDrawer open title="导出记录" width="min(860px, 100vw)" onCancel={onClose}>
    <ItsmListToolbar actions={<Button icon={<ReloadOutlined />} onClick={() => setRefresh(value => value + 1)}>刷新</Button>} />
    {error && <Alert className="mb-3" type="error" showIcon message={error} />}
    <CustomTable<TicketExportRecord> loading={loading} rowKey="id" columns={columns} dataSource={rows}
      locale={{ emptyText: '暂无导出记录' }}
      pagination={{
        total: count, current: page.current, pageSize: page.size, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100],
        onChange: (current, size) => setPage({ current: size === page.size ? current : 1, size }),
      }} />
  </ItsmDrawer>;
}
