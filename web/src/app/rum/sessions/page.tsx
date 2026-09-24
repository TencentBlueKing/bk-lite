'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  DesktopOutlined,
  MobileOutlined,
  SearchOutlined,
  TabletOutlined,
} from '@ant-design/icons';
import {
  Empty,
  Input,
  Select,
  type TableColumnsType,
} from 'antd';

import {
  useRumQueries,
  type RumSessionListPage,
  type RumSessionRow,
  type RumSessionTrendPoint,
} from '@/app/rum/api';
import CustomTable from '@/components/custom-table';
import ExportButton from '@/app/rum/components/export-button';
import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import {
  RumDualWorkbench,
  RumFilterBlock,
  RumFilterSwitchRow,
} from '@/app/rum/components/rum-dual-workbench';
import RumIconAction from '@/app/rum/components/rum-icon-action';
import RumRangeSegmented from '@/app/rum/components/rum-range-segmented';
import { RumTableSkeleton, rumSkeletonColumns } from '@/app/rum/components/rum-skeleton';
import SessionTrendChart from '@/app/rum/sessions/ui/session-trend-chart';
import TrafficScopeControl from '@/app/rum/components/traffic-scope';
import RumPageError from '@/app/rum/components/rum-page-error';
import { degradationReason } from '@/app/rum/lib/degradation';
import { resolveRumPageState } from '@/app/rum/lib/page-state';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import {
  displayRoute,
  formatDurationMs,
  parseBrowser,
  parseDevice,
  truncateMiddle,
} from '@/app/rum/lib/format';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { parseRumPageSize, RUM_DEFAULT_PAGE_SIZE } from '@/app/rum/lib/table-pagination';
import { useTranslation } from '@/utils/i18n';

type SortKey = 'impact' | 'start' | 'errors' | 'duration';

function durationMs(s: RumSessionRow): number {
  const start = Date.parse(s.startTime);
  const end = Date.parse(s.endTime || '');
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return 0;
  return end - start;
}

function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function RumSessionsPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const { range, setRange, application, setApplication, traffic, searchParams, setParams } =
    useRumSearchParams();
  const { listSessions, listSessionsTrend, listApplications, authReady } = useRumQueries();

  const [sort, setSort] = useState<SortKey>('impact');
  const [sessionId, setSessionId] = useState(searchParams.get('sessionId') || '');
  const [page, setPage] = useState<RumSessionListPage | null>(null);
  const [trend, setTrend] = useState<RumSessionTrendPoint[]>([]);
  const [apps, setApps] = useState<string[]>([]);
  const [pending, setPending] = useState(true);
  const pageNo = Math.max(1, Number(searchParams.get('page')) || 1);
  const pageSize = parseRumPageSize(searchParams.get('pageSize'));
  const hasError = searchParams.get('hasError') === '1';
  const hasReplay = searchParams.get('hasReplay') === '1';

  const query = useMemo(() => {
    const out: Record<string, string> = {
      range,
      orderBy: sort,
      limit: String(pageSize),
      offset: String((pageNo - 1) * pageSize),
      traffic,
    };
    if (application) out.application = application;
    if (sessionId.trim()) out.sessionId = sessionId.trim();
    if (hasError) out.hasError = '1';
    if (hasReplay) out.hasReplay = '1';
    return out;
  }, [range, sort, pageNo, pageSize, traffic, application, sessionId, hasError, hasReplay]);

  const load = useCallback(async () => {
    setPending(true);
    try {
      const [sessionsPage, trendPoints] = await Promise.all([
        listSessions(query),
        listSessionsTrend(query),
      ]);
      setPage(sessionsPage);
      setTrend(trendPoints);
    } catch {
      setPage(null);
      setTrend([]);
    } finally {
      setPending(false);
    }
  }, [listSessions, listSessionsTrend, query]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      setPending(true);
      void Promise.all([listSessions(query), listSessionsTrend(query)])
        .then(([sessionsPage, trendPoints]) => {
          if (isCancelled()) return;
          setPage(sessionsPage);
          setTrend(trendPoints);
        })
        .catch(() => {
          if (isCancelled()) return;
          setPage(null);
          setTrend([]);
        })
        .finally(() => {
          if (!isCancelled()) setPending(false);
        });
    },
    [listSessions, listSessionsTrend, query],
  );

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      void listApplications()
        .then((items) => {
          if (!isCancelled()) setApps(items.map((item) => item.application).filter(Boolean));
        })
        .catch(() => {
          if (!isCancelled()) setApps([]);
        });
    },
    [listApplications],
  );

  const sessions = page?.sessions || [];
  const total = page?.summary.total || 0;
  const errored = page?.summary.errored || 0;
  const medianDuration =
    page && page.summary.total > 0 ? formatDurationMs(page.summary.medianDurationMs) : '—';
  const degrade = degradationReason(page);
  const chrome = resolveRumPageState({
    // Refetch (range / filter change) must also enter loading chrome; otherwise
    // stale rows stay on screen with no feedback while the network is in flight.
    pending,
    error: !pending && page === null ? t('rum.sessions.loadFailed', '会话列表加载失败') : null,
    itemCount: sessions.length,
    page,
  });

  const columns: TableColumnsType<RumSessionRow> = [
    {
      title: t('rum.sessions.landingPage', '落地页'),
      key: 'landing',
      ellipsis: true,
      render: (_, s) => {
        const landing = displayRoute(s.entryRoute) || t('rum.sessions.landingPageUnknown', '未知落地页');
        const href = `/rum/sessions/${encodeURIComponent(s.sessionId)}?application=${encodeURIComponent(s.application)}&range=${range}`;
        return (
          <div className="flex min-w-0 flex-col gap-0.5">
            <Link
              href={href}
              className="truncate hover:text-[var(--color-primary)] hover:underline"
              title={displayRoute(s.entryRoute) || undefined}
              onClick={(e) => e.stopPropagation()}
            >
              {landing}
            </Link>
            <span className="truncate text-xs tabular-nums text-[var(--color-text-3)]" title={s.sessionId}>
              {truncateMiddle(s.sessionId, 18)}
            </span>
          </div>
        );
      },
    },
    {
      title: t('rum.sessions.user', '用户'),
      key: 'user',
      width: 120,
      render: (_, s) =>
        s.userId ? (
          <span className="truncate" title={s.userId}>
            {truncateMiddle(s.userId, 18)}
          </span>
        ) : (
          <span>{t('rum.sessions.anonymous', '匿名')}</span>
        ),
    },
    {
      title: t('rum.sessions.viewsCount', '浏览'),
      key: 'views',
      width: 72,
      render: (_, s) => <span className="tabular-nums">{s.viewCount}</span>,
    },
    {
      title: t('rum.sessions.duration', '时长'),
      key: 'duration',
      width: 88,
      render: (_, s) => formatDurationMs(durationMs(s)),
    },
    {
      title: t('rum.sessions.errors', '错误'),
      key: 'errors',
      width: 72,
      render: (_, s) => (
        <span className={`tabular-nums ${s.errorCount > 0 ? 'text-[var(--color-fail)]' : ''}`}>
          {s.errorCount}
        </span>
      ),
    },
    {
      title: t('rum.sessions.environment', '环境'),
      key: 'environment',
      width: 120,
      render: (_, s) => {
        const ua = s.userAgent || '';
        const device = parseDevice(ua);
        const Icon =
          device === 'mobile' ? MobileOutlined : device === 'tablet' ? TabletOutlined : DesktopOutlined;
        return (
          <span
            className="inline-flex items-center gap-1.5"
            title={`${device} · ${parseBrowser(ua)}`}
          >
            <Icon />
            <span>{parseBrowser(ua)}</span>
          </span>
        );
      },
    },
    {
      title: t('rum.sessions.started', '开始时间'),
      key: 'started',
      width: 128,
      render: (_, s) => (
        <span className="tabular-nums">{formatWhen(s.startTime)}</span>
      ),
    },
    {
      title: t('rum.common.actions', '操作'),
      key: 'actions',
      width: 80,
      fixed: 'right',
      render: (_, s) =>
        s.hasReplay ? (
          <RumIconAction
            title={t('rum.sessions.replayAction', '回放')}
            onClick={(e) => {
              e.stopPropagation();
              router.push(
                `/rum/sessions/${encodeURIComponent(s.sessionId)}/replay?application=${encodeURIComponent(s.application)}`,
              );
            }}
          />
        ) : (
          <span className="text-[var(--color-text-4)]">—</span>
        ),
    },
  ];

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t('rum.sessions.title', '会话')}</h1>

      {degrade ? <div className="mb-2 shrink-0"><PipelineDegradedBanner reason={degrade} /></div> : null}

      <RumDualWorkbench
        asideTitle={t('rum.sessions.quickFilter', '快速筛选')}
        aside={
          <>
            <RumFilterBlock title={t('rum.common.timeWindow', '时间')}>
              <RumRangeSegmented
                block
                size="small"
                value={range}
                loading={pending}
                onChange={setRange}
              />
            </RumFilterBlock>
            <RumFilterBlock title={t('rum.applications.application', '应用')}>
              <Select
                allowClear
                showSearch
                size="small"
                className="w-full"
                placeholder={t('rum.filter.allApps', '全部应用')}
                value={application || undefined}
                onChange={(value) => setApplication(value || '')}
                options={apps.map((name) => ({ value: name, label: name }))}
              />
            </RumFilterBlock>
            <div className="space-y-2.5 border-t border-[var(--color-fill-2)] pt-3">
              <RumFilterSwitchRow
                label={t('rum.sessions.onlyErrors', '仅看错误')}
                checked={hasError}
                onChange={(v) => setParams({ hasError: v ? '1' : null, page: null })}
              />
              <RumFilterSwitchRow
                label={t('rum.sessions.onlyReplay', '仅看回放')}
                checked={hasReplay}
                onChange={(v) => setParams({ hasReplay: v ? '1' : null, page: null })}
              />
            </div>
            <RumFilterBlock title={t('rum.traffic.label', '流量')}>
              <TrafficScopeControl block size="small" />
            </RumFilterBlock>
          </>
        }
        mainTitle={t('rum.sessions.detailTitle', '会话明细')}
        mainExtra={
          page && !pending ? (
            <>
              <span className="tabular-nums text-[var(--color-text-2)]">
                {t('rum.sessions.kpi.total', '全部会话')} {total}
              </span>
              <button
                type="button"
                className={`tabular-nums ${errored > 0 ? 'text-[var(--color-fail)]' : 'text-[var(--color-text-3)]'}`}
                onClick={() => setParams({ hasError: hasError ? null : '1', page: null })}
              >
                {t('rum.sessions.kpi.errored', '错误会话')} {errored}
              </button>
              <span className="tabular-nums text-[var(--color-text-3)]">
                {t('rum.sessions.kpi.medianDuration', '中位时长')} {medianDuration}
              </span>
            </>
          ) : null
        }
        main={
          chrome === 'loading' ? (
            <RumTableSkeleton columns={rumSkeletonColumns(columns)} />
          ) : chrome === 'error' ? (
            <div className="flex min-h-0 flex-1 items-center justify-center">
              <RumPageError
                message={t('rum.sessions.loadFailed', '会话列表加载失败')}
                onRetry={() => void load()}
              />
            </div>
          ) : (
            <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
              {page ? (
                <div className="shrink-0 border-b border-[var(--color-fill-2)] pb-2.5">
                  <div className="mb-1.5 text-[11px] text-[var(--color-text-3)]">
                    {t('rum.sessions.trend', '会话趋势')}
                  </div>
                  <SessionTrendChart points={trend} compact hideTitle />
                </div>
              ) : null}

              <div className="flex h-8 shrink-0 flex-wrap items-center justify-end gap-2">
                <Select
                  value={sort}
                  className="h-8 w-[120px] [&_.ant-select-selector]:!h-8 [&_.ant-select-selector]:!items-center"
                  onChange={(value) => {
                    setSort(value as SortKey);
                    setParams({ page: null });
                  }}
                  options={[
                    { value: 'impact', label: t('rum.sessions.sortImpact', '影响力') },
                    { value: 'start', label: t('rum.sessions.sortStart', '开始时间') },
                    { value: 'errors', label: t('rum.sessions.sortErrors', '错误数') },
                    { value: 'duration', label: t('rum.sessions.sortDuration', '时长') },
                  ]}
                />
                <Input
                  allowClear
                  className="!h-8 w-60 !items-center !py-0"
                  placeholder={t('rum.sessions.searchPlaceholder', '搜索会话 ID')}
                  prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
                  value={sessionId}
                  onChange={(e) => setSessionId(e.target.value)}
                  onPressEnter={() => {
                    setParams({ sessionId: sessionId.trim() || null, page: null });
                    void load();
                  }}
                />
                <ExportButton
                  rows={(page?.sessions || []) as unknown as Record<string, unknown>[]}
                  filename="rum-sessions"
                  truncated={total > (page?.sessions?.length || 0)}
                  truncatedLimit={page?.sessions?.length || 0}
                />
              </div>

              {!pending && sessions.length === 0 ? (
                <div className="flex min-h-0 flex-1 items-center justify-center">
                  <Empty description={t('rum.sessions.empty', '没有匹配的会话')} />
                </div>
              ) : sessions.length > 0 ? (
                <div className="min-h-0 min-w-0 flex-1">
                  <CustomTable<RumSessionRow>
                    rowKey={(r) => `${r.application}:${r.sessionId}`}
                    dataSource={sessions}
                    tableLayout="fixed"
                    size="middle"
                    autoScrollX={false}
                    columns={columns}
                    pagination={{
                      current: pageNo,
                      pageSize,
                      total,
                      showSizeChanger: true,
                      onChange: (nextPage, nextSize) => {
                        const size = parseRumPageSize(nextSize);
                        setParams(
                          {
                            page: nextPage <= 1 ? null : String(nextPage),
                            pageSize: size === RUM_DEFAULT_PAGE_SIZE ? null : String(size),
                          },
                          { replace: true },
                        );
                      },
                    }}
                    onRow={(s) => ({
                      onClick: () =>
                        router.push(
                          `/rum/sessions/${encodeURIComponent(s.sessionId)}?application=${encodeURIComponent(s.application)}&range=${range}`,
                        ),
                      className: 'cursor-pointer transition-colors hover:bg-[var(--color-fill-2)]',
                    })}
                  />
                </div>
              ) : null}
            </div>
          )
        }
      />
    </div>
  );
}
