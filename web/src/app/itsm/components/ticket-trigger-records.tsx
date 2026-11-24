'use client';

import { Alert, Button, Empty, Pagination, Skeleton, Tag } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from '@/utils/i18n';
import { useItsmApi, type TicketTriggerLogPage } from '../api/useItsmApi';
import { formatTicketTime } from './ticket-collaboration';

const STATUS = {
  success: { color: 'success', label: 'triggerRecordSuccess' },
  failed: { color: 'error', label: 'triggerRecordFailed' },
  pending: { color: 'processing', label: 'triggerRecordPending' },
  legacy: { color: 'default', label: 'triggerRecordLegacy' },
};
const ACTION_LABELS: Record<string, string> = { tag: 'tag', notice: 'notice', status: 'changeStatus' };

export function TicketTriggerRecords({ ticketId, refreshKey }: { ticketId: number; refreshKey: number }) {
  const { t } = useTranslation();
  const { getTicketTriggerLogs, ready } = useItsmApi();
  const [{ page, pageSize }, setPage] = useState({ page: 1, pageSize: 20 });
  const [retry, setRetry] = useState(0);
  const key = `${ticketId}:${page}:${pageSize}:${refreshKey}:${retry}`;
  const request = useRef<{ key: string; promise: Promise<TicketTriggerLogPage> }>(null);
  const [response, setResponse] = useState<{ key: string; data?: TicketTriggerLogPage }>();

  useEffect(() => {
    if (!ready) return;
    let active = true;
    if (request.current?.key !== key) {
      request.current = { key, promise: getTicketTriggerLogs(ticketId, page, pageSize) };
    }
    void request.current.promise.then(
      data => { if (active) setResponse({ key, data }); },
      () => { if (active) setResponse({ key }); },
    );
    return () => { active = false; };
  }, [getTicketTriggerLogs, key, page, pageSize, ready, ticketId]);

  if (response?.key !== key) {
    return <div aria-busy className="py-3"><Skeleton active title={{ width: '55%' }} paragraph={{ rows: 2 }} /></div>;
  }
  const { data } = response;
  if (!data) {
    return <Alert className="mt-3" type="error" showIcon message={t('itsm.ticket.triggerRecordsLoadFailed')}
      action={<Button size="small" onClick={() => setRetry(value => value + 1)}>{t('common.retry')}</Button>} />;
  }
  if (!data.items.length) {
    return <Empty className="mt-6" image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('itsm.ticket.noTriggerRecords')} />;
  }

  return <div className="flex min-w-0 flex-col gap-3 py-3">
    <ul role="list" aria-label={t('itsm.ticket.triggerRecords')} className="divide-y divide-[var(--color-border)]">
      {data.items.map(record => {
        const status = STATUS[record.status] ?? STATUS.legacy;
        const action = ACTION_LABELS[record.action];
        return <li key={record.id} className="flex min-w-0 flex-col gap-1 py-3 first:pt-0">
          <div className="flex items-start justify-between gap-3">
            <span className="min-w-0 wrap-anywhere font-medium text-[var(--color-text-1)]">{record.trigger_name}</span>
            <Tag color={status.color} className="!m-0 shrink-0">{t(`itsm.ticket.${status.label}`)}</Tag>
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--color-text-3)]">
            <span>{t(`itsm.rule.${record.event}`, record.event)}</span>
            {record.position && <span>{t('itsm.ticket.triggerRecordPosition', undefined, { position: record.position })}</span>}
            {record.action && <span>{action ? t(`itsm.rule.${action}`) : record.action}</span>}
            <time dateTime={record.created_at} className="tabular-nums">{formatTicketTime(record.created_at)}</time>
          </div>
          {record.message && <p className="!m-0 whitespace-pre-wrap wrap-anywhere text-sm text-[var(--color-text-2)]">{record.message}</p>}
        </li>;
      })}
    </ul>
    <Pagination className="justify-end" size="small" current={page} pageSize={pageSize} total={data.count}
      showSizeChanger pageSizeOptions={[10, 20, 50, 100]}
      showTotal={total => `${t('common.total')} ${total} ${t('common.items')}`}
      onChange={(next, size) => setPage({ page: size === pageSize ? next : 1, pageSize: size })} />
  </div>;
}
