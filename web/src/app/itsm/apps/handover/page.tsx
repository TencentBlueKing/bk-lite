'use client';

import { useEffect, useRef, useState } from 'react';
import { Alert, Button, Table, Tag, type TableColumnsType } from 'antd';
import dayjs from 'dayjs';
import { useItsmApi } from '../../api/useItsmApi';
import { ItsmModal } from '../../components/interaction-surfaces';
import ItsmListTable from '../../components/itsm-list-table';
import { ItsmCreateButton, ItsmListToolbar, ItsmRowActions } from '../../components/list-controls';
import type { HandoverRecord, HandoverResult, HandoverResultStatus } from '../../types';
import { HandoverForm } from './handover-form';

const STATUS: Record<HandoverResultStatus, { label: string; color: string }> = {
  pending: { label: '待处理', color: 'default' },
  succeeded: { label: '成功', color: 'success' },
  failed: { label: '失败', color: 'error' },
  skipped: { label: '跳过', color: 'default' },
  unconfirmed: { label: '待核对', color: 'warning' },
};

function Summary({ results }: { results?: HandoverResult[] }) {
  const counts = new Map<HandoverResultStatus, number>();
  for (const result of results || []) {
    counts.set(result.status, (counts.get(result.status) || 0) + 1);
  }
  return results?.length ? <div className="flex flex-wrap gap-y-1">
    {(Object.keys(STATUS) as HandoverResultStatus[]).map(key => counts.has(key)
      ? <Tag key={key} color={STATUS[key].color}>{STATUS[key].label} {counts.get(key)}</Tag> : null)}
  </div> : '—';
}

function HandoverResults({ record, canRetry, onRetry, onClose }: {
  record: HandoverRecord;
  canRetry: boolean;
  onRetry: () => Promise<void>;
  onClose: () => void;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const retrying = useRef(false);
  const results = record.results || [];
  const hasRetryable = results.some(row => row.status === 'pending' || row.status === 'failed');
  const retry = async () => {
    if (!canRetry || !hasRetryable || retrying.current) return;
    retrying.current = true;
    setPending(true);
    setError('');
    try {
      await onRetry();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : '无法重试交接，请稍后再试');
    } finally {
      retrying.current = false;
      setPending(false);
    }
  };
  return <ItsmModal open width={720} title="交接结果" confirmLoading={pending} onCancel={onClose}
    footer={<>
      <Button disabled={pending} onClick={onClose}>关闭结果</Button>
      {canRetry && hasRetryable && <Button type="primary" loading={pending} onClick={() => void retry()}>重试失败或待处理项</Button>}
    </>}>
    <div className="flex flex-col gap-3 py-2">
      <div>{record.from_user} → {record.to_user}</div>
      <Summary results={results} />
      {results.some(row => row.status === 'unconfirmed') &&
        <Alert type="warning" showIcon message="待核对项需确认实际处理人，暂时不可重试" />}
      {error && <Alert type="error" showIcon message={error} />}
      <Table<HandoverResult> rowKey={row => `${row.ticket_id}:${row.task_id ?? ''}`} size="small"
        scroll={{ y: 360 }} pagination={false} dataSource={results} locale={{ emptyText: '历史记录无逐项结果' }}
        columns={[
          { title: '工单 ID', dataIndex: 'ticket_id', width: 90 },
          { title: '任务 ID', dataIndex: 'task_id', width: 90, render: value => value ?? '—' },
          { title: '状态', dataIndex: 'status', width: 90, render: (status: HandoverResultStatus) =>
            <Tag color={STATUS[status]?.color}>{STATUS[status]?.label || '—'}</Tag> },
          { title: '说明', dataIndex: 'message', render: value => value || '—' },
        ]} />
    </div>
  </ItsmModal>;
}

export default function Page() {
  const { ready, listHandovers, retryHandover } = useItsmApi();
  const [rows, setRows] = useState<HandoverRecord[]>([]);
  const [permissions, setPermissions] = useState({ create: false, retry: false });
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [keyword, setKeyword] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [resultId, setResultId] = useState<number>();
  const record = rows.find(row => row.id === resultId);

  useEffect(() => {
    if (!ready) return;
    let active = true;
    setLoading(true);
    setFailed(false);
    void listHandovers().then(data => {
      if (!active) return;
      setRows(data.items);
      setPermissions({ create: data.can_add === true, retry: data.can_retry === true });
    }).catch(() => {
      if (active) setFailed(true);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [ready, listHandovers, refresh]);

  const columns: TableColumnsType<HandoverRecord> = [
    { title: '交出人', dataIndex: 'from_user' },
    { title: '接收人', dataIndex: 'to_user' },
    { title: '工单数', align: 'right', render: (_, row) => Array.isArray(row.ticket_ids) ? row.ticket_ids.length : '—' },
    { title: '执行结果', render: (_, row) => <Summary results={row.results} /> },
    { title: '创建时间', dataIndex: 'created_at', width: 180, render: value => value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '—' },
    { title: '操作', width: 100, render: (_, row) => <ItsmRowActions items={[
      { key: 'result', label: '查看交接结果', kind: 'history', onClick: () => setResultId(row.id) },
    ]} /> },
  ];
  const filteredRows = rows.filter(row => `${row.from_user} ${row.to_user}`.toLowerCase().includes(keyword.trim().toLowerCase()));

  return <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
    <ItsmListToolbar search={{ value: keyword, onChange: setKeyword, label: '搜索交接', placeholder: '搜索交出人或接收人' }}
      actions={permissions.create && <ItsmCreateButton onClick={() => setCreateOpen(true)}>新建交接</ItsmCreateButton>} />
    {failed && <Alert className="mb-3" type="error" showIcon message="交接记录加载失败"
      action={<Button size="small" onClick={() => setRefresh(value => value + 1)}>重新加载</Button>} />}
    <ItsmListTable<HandoverRecord> loading={loading} rowKey="id" columns={columns} queryKey={keyword}
      dataSource={filteredRows} locale={{ emptyText: '暂无交接记录' }} />
    {createOpen && permissions.create && <HandoverForm onClose={() => setCreateOpen(false)} onCreated={created => {
      setRows(current => [created, ...current]);
      setCreateOpen(false);
      setResultId(created.id);
    }} />}
    {record && <HandoverResults key={record.id} record={record} canRetry={permissions.retry} onClose={() => setResultId(undefined)}
      onRetry={async () => {
        const updated = await retryHandover(record.id);
        setRows(current => current.map(row => row.id === updated.id ? updated : row));
      }} />}
  </div>;
}
