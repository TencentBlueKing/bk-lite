import type { TicketJobProgress, TicketJobRecord } from '../types';

const statusLabels: Record<string, string> = {
  pending: '等待执行', running: '执行中', cancelling: '取消中',
  success: '成功', failed: '失败', timeout: '超时', cancelled: '已取消',
};
const terminal = new Set(['success', 'failed', 'timeout', 'cancelled']);

export function jobProgressLabel(progress: TicketJobProgress, records: TicketJobRecord[]) {
  if (progress.mode === 'once') return '单次执行';
  const { total, batch_size: size } = progress;
  const parallel = progress.dispatch_mode === 'parallel' || (!progress.dispatch_mode && !size);
  if (!total) return parallel ? '并发执行' : `逐项执行 · 每批 ${size} 项`;
  const completed = records.filter(record => terminal.has(record.status || '')).length;
  const dispatched = Math.max(0, ...records.map(record => record.row));
  const batch = size && size < total && dispatched ? ` · 第 ${Math.ceil(dispatched / size)}/${Math.ceil(total / size)} 批` : '';
  return `${parallel ? '并发执行 · ' : ''}已完成 ${completed}/${total} 项${batch}`;
}

export function TicketJobRecords({ progress, records }: { progress: TicketJobProgress; records: TicketJobRecord[] }) {
  const byRow = new Map(records.map(record => [record.row, record]));
  const total = progress.total ?? records.length;
  return <ol aria-label="逐项作业记录" className="m-0 max-h-64 overflow-y-auto p-0 text-xs">
    {Array.from({ length: total }, (_, index) => {
      const row = index + 1;
      const record = byRow.get(row);
      return <li key={row} className="flex items-center gap-2 border-b border-[var(--color-border)] py-1.5 last:border-b-0">
        {progress.mode === 'each' && <span>第 {row} 项</span>}
        <span>{record ? statusLabels[record.status || ''] || '已派发' : '未派发'}</span>
        {record && <a className="ml-auto" target="_blank" rel="noopener noreferrer" href={`/job/execution/job-record?id=${record.job_id}`}>作业 #{record.job_id}</a>}
      </li>;
    })}
  </ol>;
}
