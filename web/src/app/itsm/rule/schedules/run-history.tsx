'use client';

import { Alert, Button, Tag } from 'antd';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { useItsmApi } from '../../api/useItsmApi';
import { ItsmDrawer } from '../../components/interaction-surfaces';
import CustomTable from '@/components/custom-table';
import { formatTicketTime } from '../../components/ticket-collaboration';

export interface ScheduleHistoryTarget {
  id?: number;
  name?: string;
}

interface ScheduleRun {
  id: number;
  schedule_name: string;
  status: 'running' | 'succeeded' | 'failed' | 'unconfirmed';
  due_at: string;
  finished_at: string | null;
  message: string;
  ticket_id: number | null;
}

const STATUS = {
  running: { label: '执行中', color: 'processing' },
  succeeded: { label: '成功', color: 'success' },
  failed: { label: '失败', color: 'error' },
  unconfirmed: { label: '结果待核对', color: 'warning' },
};

export function ScheduleRunHistory({ target, onClose }: { target: ScheduleHistoryTarget; onClose: () => void }) {
  const { listScheduleRuns } = useItsmApi();
  const [page, setPage] = useState(1);
  const [revision, refresh] = useState(0);
  const [rows, setRows] = useState<ScheduleRun[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(() => listScheduleRuns(page, target.id), [listScheduleRuns, page, target.id]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    void load().then((response) => {
      if (!active) return;
      const result = response as { items: ScheduleRun[]; count: number };
      setRows(result.items);
      setCount(result.count);
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : '读取执行记录失败');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [load, revision]);

  return <ItsmDrawer open title={target.name ? `执行记录 · ${target.name}` : '定时任务执行记录'} onCancel={onClose}>
    <div className="mb-3 flex justify-end"><Button onClick={() => refresh(value => value + 1)}>刷新记录</Button></div>
    {error && <Alert className="mb-3" type="error" message={error} />}
    <CustomTable<ScheduleRun> rowKey="id" loading={loading} dataSource={rows}
      pagination={{ current: page, pageSize: 20, total: count, showSizeChanger: false, onChange: setPage }}
      columns={[
        { title: '任务', dataIndex: 'schedule_name' },
        { title: '计划时间', dataIndex: 'due_at', render: formatTicketTime },
        { title: '完成时间', dataIndex: 'finished_at', render: value => value ? formatTicketTime(value) : '—' },
        { title: '状态', dataIndex: 'status', render: (_value, row) => <Tag color={STATUS[row.status].color}>{STATUS[row.status].label}</Tag> },
        { title: '工单', dataIndex: 'ticket_id', render: (_value, row) => row.ticket_id ? <Link href={`/itsm/tickets/${row.ticket_id}`}>查看工单</Link> : '—' },
        { title: '执行说明', dataIndex: 'message', render: value => value || '—' },
      ]}
    />
  </ItsmDrawer>;
}
