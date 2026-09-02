'use client';

import Link from 'next/link';
import { Tag, Typography } from 'antd';
import { formatDateTime, formatLatency, formatRelativeTime } from '@/app/apm/components/metric-format';
import type { ApmIssue } from '@/app/apm/types';
import { useTranslation } from '@/utils/i18n';

function Distribution({ items }: { items: ApmIssue['version_distribution'] }) {
  if (!items.length) return <span className="text-xs text-[var(--color-text-3)]">—</span>;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--color-text-2)]">
      {items.map((item) => (
        <span key={item.value}>
          <span className="font-mono">{item.value}</span>
          <span className="text-[var(--color-text-3)]"> · {item.count} ({item.percent}%)</span>
        </span>
      ))}
    </div>
  );
}

function IssueDetails({ issue }: { issue: ApmIssue }) {
  const { t } = useTranslation();
  return (
    <details>
      <summary className="cursor-pointer select-none text-sm text-[var(--color-text-2)] hover:text-[var(--color-text-1)]">
        {t('apm.errors.issueDetails', '完整堆栈与分布')}
      </summary>
      <div className="mt-3 flex flex-col gap-4">
        {issue.stacktrace ? (
          <pre className="m-0 max-h-80 overflow-auto whitespace-pre-wrap font-mono text-xs leading-5 text-[var(--color-text-2)]">
            {issue.stacktrace}
          </pre>
        ) : (
          <p className="m-0 text-xs text-[var(--color-text-3)]">{t('apm.errors.noStacktrace', '遥测中未携带异常堆栈')}</p>
        )}
        <div className="flex flex-wrap gap-x-10 gap-y-4">
          <div className="flex min-w-[200px] flex-col gap-1.5">
            <div className="text-xs text-[var(--color-text-3)]">{t('apm.errors.versionDistribution', '版本分布')}</div>
            <Distribution items={issue.version_distribution} />
          </div>
          <div className="flex min-w-[200px] flex-col gap-1.5">
            <div className="text-xs text-[var(--color-text-3)]">{t('apm.errors.endpointDistribution', '端点分布')}</div>
            <Distribution items={issue.endpoint_distribution} />
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <div className="text-xs text-[var(--color-text-3)]">{t('apm.errors.sampleTraces', '样本调用链')}</div>
          <div className="flex flex-col gap-1">
            {issue.sample_traces.map((sample) => (
              <Link
                key={`${sample.trace_id}:${sample.span_id}`}
                href={`/apm/explore/traces/${sample.trace_id}`}
                className="inline-flex max-w-full flex-wrap items-baseline gap-x-2 text-[var(--color-text-1)] hover:text-[var(--color-primary)]"
              >
                <span className="font-mono text-xs">{sample.endpoint}</span>
                {' '}
                <span className="text-xs text-[var(--color-text-3)]">
                  {formatLatency(sample.duration_ms, false, t)} · {formatDateTime(sample.started_at)}
                </span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </details>
  );
}

export default function ApmIssueList({
  items,
  showService = true,
}: {
  items: ApmIssue[];
  showService?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="divide-y divide-[var(--color-border)]">
      {items.map((issue) => (
        <article key={issue.fingerprint} className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0">
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <Typography.Text strong className="!text-base">{issue.exception_type}</Typography.Text>
              <Tag color="error">{t('apm.errors.occurrences', '{count} 次', { count: issue.occurrences })}</Tag>
              <Tag>{t('apm.errors.affectedTraces', '{count} 条 Trace', { count: issue.affected_traces })}</Tag>
              <Typography.Text type="secondary" className="!text-xs">{formatRelativeTime(issue.last_seen_at, t)}</Typography.Text>
            </div>
            <Typography.Paragraph className="!mb-0 break-words !text-sm">{issue.message}</Typography.Paragraph>
            {showService ? (
              <Typography.Text type="secondary" className="!text-xs">
                {issue.service_namespace} / {issue.service_name} · {issue.environment || t('apm.common.unset', '未设置')}
              </Typography.Text>
            ) : null}
          </div>
          <IssueDetails issue={issue} />
        </article>
      ))}
    </div>
  );
}
