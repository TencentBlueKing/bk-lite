'use client';

import { Empty, Tag } from 'antd';
import type { TicketSLAItem } from '../types';
import { formatTicketTime } from './ticket-collaboration';

const RESULT = {
  sent: { label: '已发送', color: 'success' },
  failed: { label: '发送失败', color: 'error' },
  skipped: { label: '已跳过', color: 'default' },
};

export function TicketSla({ records }: { records: TicketSLAItem[] }) {
  if (!records.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前工单未配置 SLA" />;
  return <div className="flex flex-col gap-4 py-3">
    {records.map(record => {
      const label = record.target === 'response' ? '响应时限' : '解决时限';
      const status = record.paused ? '已暂停' : record.breached ? '已超时' : record.finished_at ? '已达标' : '计时中';
      const color = record.paused ? 'default' : record.breached ? 'error' : record.finished_at ? 'success' : 'processing';
      return <section key={record.target} aria-label={label} className="rounded-md border border-[var(--color-border)] p-3">
        <div className="flex items-center justify-between gap-2"><span className="font-medium">{label}</span><Tag color={color}>{status}</Tag></div>
        <div className="mt-2 flex flex-col gap-1 text-xs text-[var(--color-text-3)]">
          {record.warning_at && <span>预警时间 {formatTicketTime(record.warning_at)}</span>}
          <time dateTime={record.due_at}>截止时间 {formatTicketTime(record.due_at)}</time>
        </div>
        <ul aria-label={`${label}执行记录`} className="mt-3 flex flex-col gap-3">
          {record.notices?.map(notice => <li key={notice.id} className="flex flex-col gap-1 border-t border-[var(--color-border)] pt-2">
            <div className="flex flex-wrap items-center gap-2">
              <span>{notice.kind === 'warning' ? '超时预警' : '超时升级'}</span>
              <Tag color={RESULT[notice.status].color}>{RESULT[notice.status].label}</Tag>
            </div>
            <span className="text-xs text-[var(--color-text-3)]">{formatTicketTime(notice.triggered_at)}</span>
            <div className="flex flex-wrap gap-1">{notice.recipients.map(user => <Tag key={user}>{user}</Tag>)}</div>
            {notice.message && <span className="text-xs text-[var(--color-text-3)]">{notice.message}</span>}
          </li>)}
          {!record.notices?.length && <li className="text-xs text-[var(--color-text-3)]">暂无通知记录</li>}
        </ul>
      </section>;
    })}
  </div>;
}
