'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Alert, Button, Select, Tag, Typography } from 'antd';
import useApmApi from '@/app/apm/api';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState, { catalogErrorKind, type CatalogStateKind } from '@/app/apm/components/catalog-state';
import { formatDateTime, formatLatency, formatRelativeTime } from '@/app/apm/components/metric-format';
import type { ApmIssue, ApmService } from '@/app/apm/types';
import FilterToolbar from '@/components/filter-toolbar';
import { useTranslation } from '@/utils/i18n';

type PageState = CatalogStateKind | 'ready';
type TimeRange = '15m' | '1h' | '4h' | '1d' | '7d';
const RANGE_MS: Record<TimeRange, number> = { '15m': 900000, '1h': 3600000, '4h': 14400000, '1d': 86400000, '7d': 604800000 };

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

export default function ApmErrorsPage() {
  const { t } = useTranslation();
  const { getIssues, getServices, isLoading: authLoading } = useApmApi();
  const [services, setServices] = useState<ApmService[]>([]);
  const [serviceId, setServiceId] = useState<string>();
  const [environment, setEnvironment] = useState<string>();
  const [timeRange, setTimeRange] = useState<TimeRange>('1h');
  const [items, setItems] = useState<ApmIssue[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [state, setState] = useState<PageState>('loading');
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    if (!authLoading) void getServices().then(setServices).catch(() => setServices([]));
  }, [authLoading, getServices]);
  const environments = useMemo(() => Array.from(new Set(services.flatMap((service) => service.environment_views.map((view) => view.environment)))).sort(), [services]);
  const selectedService = useMemo(() => services.find((service) => service.id === serviceId), [serviceId, services]);
  const load = useCallback((cursor?: string) => {
    if (authLoading) return;
    if (cursor) setLoadingMore(true); else setState('loading');
    const endedAt = new Date();
    const startedAt = new Date(endedAt.getTime() - RANGE_MS[timeRange]);
    void getIssues({ service_namespace: selectedService?.namespace, service_name: selectedService?.name, environment, started_at: startedAt.toISOString(), ended_at: endedAt.toISOString(), cursor, limit: 50 })
      .then((page) => {
        setItems((current) => cursor ? [...current, ...page.items] : page.items);
        setNextCursor(page.next_cursor); setTruncated(page.truncated);
        setState(page.items.length || cursor || page.next_cursor ? 'ready' : 'empty');
      }).catch((error) => setState(catalogErrorKind(error))).finally(() => setLoadingMore(false));
  }, [authLoading, environment, getIssues, selectedService, timeRange]);
  useEffect(() => { load(); }, [load]);

  return (
    <ApmRouteShell title={t('apm.errors.title', '错误分析')} description={t('apm.errors.description', '按真实异常语义聚类 Error Span，并下钻版本、端点和样本 Trace。')}>
      <ApmSurface>
        <div className="flex flex-col gap-4">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
            <Select className="w-52" allowClear showSearch optionFilterProp="label" placeholder={t('apm.errors.allServices', '全部服务')} value={serviceId} options={services.map((service) => ({ value: service.id, label: `${service.namespace} / ${service.name}` }))} onChange={setServiceId} />
            <Select className="w-44" allowClear showSearch placeholder={t('apm.errors.allEnvironments', '全部环境')} value={environment} options={environments.map((value) => ({ value, label: value || t('apm.common.unset', '未设置') }))} onChange={setEnvironment} />
            <Select<TimeRange> className="w-28" value={timeRange} options={(Object.keys(RANGE_MS) as TimeRange[]).map((value) => ({ value, label: value }))} onChange={setTimeRange} />
          </FilterToolbar>
          {truncated ? <Alert showIcon type="info" message={t('apm.errors.boundedHint', '结果按时间窗和游标有界展示，可继续加载更早样本。')} /> : null}
          {state === 'ready' ? (
            <div className="flex flex-col gap-4">
              {!items.length ? <CatalogState kind="empty" description={t('apm.errors.emptyPage', '当前游标页没有可见 Issue，可继续加载更早样本。')} /> : null}
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
                      <Typography.Text type="secondary" className="!text-xs">{issue.service_namespace} / {issue.service_name} · {issue.environment || t('apm.common.unset', '未设置')}</Typography.Text>
                    </div>
                    <IssueDetails issue={issue} />
                  </article>
                ))}
              </div>
              {nextCursor ? <Button loading={loadingMore} onClick={() => load(nextCursor)}>{t('apm.common.loadMore', '加载更多')}</Button> : null}
            </div>
          ) : state === 'empty' ? (
            <CatalogState kind="empty" description={t('apm.errors.empty', '当前权限和时间窗内没有错误 Issue。')} />
          ) : (
            <CatalogState kind={state} onRetry={state === 'forbidden' ? undefined : () => load()} />
          )}
        </div>
      </ApmSurface>
    </ApmRouteShell>
  );
}
