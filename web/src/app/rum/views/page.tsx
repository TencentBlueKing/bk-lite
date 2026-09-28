'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CaretDownOutlined, SearchOutlined, SwapOutlined } from '@ant-design/icons';
import { Empty, Input, Segmented, Select, type TableColumnsType } from 'antd';

import {
  useRumQueries,
  type RumViewAggregateRow,
  type RumViewListPage,
} from '@/app/rum/api';
import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import ExportButton from '@/app/rum/components/export-button';
import {
  RumDualWorkbench,
  RumFilterBlock,
} from '@/app/rum/components/rum-dual-workbench';
import RumRangeSegmented from '@/app/rum/components/rum-range-segmented';
import { RumTableSkeleton, rumSkeletonColumns } from '@/app/rum/components/rum-skeleton';
import TrafficScopeControl from '@/app/rum/components/traffic-scope';
import { cwvTone, formatMs, toneSemanticPalette, toneTextClass, type CwvTone } from '@/app/rum/lib/cwv';
import SemanticBadge from '@/components/semantic-badge';
import { degradationReason } from '@/app/rum/lib/degradation';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import { useRumClientPager } from '@/app/rum/lib/table-pagination';
import DeviceMixCell from '@/app/rum/views/ui/device-mix-cell';
import DistributionBar from '@/app/rum/views/ui/distribution-bar';
import MomCell from '@/app/rum/views/ui/mom-cell';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';

type SortKey = 'impact' | 'views' | 'lcp' | 'inp' | 'cls';
type Mode = 'route' | 'release';

function sortRows(rows: RumViewAggregateRow[], key: SortKey): RumViewAggregateRow[] {
  const field: Record<SortKey, (r: RumViewAggregateRow) => number> = {
    impact: (r) => r.impact,
    views: (r) => r.views,
    lcp: (r) => r.lcpP75,
    inp: (r) => r.inpP75,
    cls: (r) => r.clsP75,
  };
  return [...rows].sort((a, b) => field[key](b) - field[key](a));
}

function rootCauseTone(row: RumViewAggregateRow): { labelKey: string; tone: CwvTone } {
  if (row.views < 20) return { labelKey: 'lowSample', tone: 'neutral' };
  const lcp = cwvTone('lcp', row.lcpP75);
  const inp = cwvTone('inp', row.inpP75);
  if (lcp === 'danger' || inp === 'danger') return { labelKey: 'poor', tone: 'danger' };
  if (lcp === 'warning' || inp === 'warning') return { labelKey: 'watch', tone: 'warning' };
  return { labelKey: 'ok', tone: 'success' };
}

export default function RumViewsPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const {
    range,
    setRange,
    application,
    setApplication,
    traffic,
    searchParams,
    setParams,
  } = useRumSearchParams();
  const { listViews, listApplications, authReady } = useRumQueries();

  const mode = ((searchParams.get('mode') as Mode) || 'route') === 'release' ? 'release' : 'route';
  const release = searchParams.get('release') || '';
  const [sort, setSort] = useState<SortKey>('impact');
  const [routeQuery, setRouteQuery] = useState('');
  const [page, setPage] = useState<RumViewListPage | null>(null);
  const [apps, setApps] = useState<string[]>([]);
  const [pending, setPending] = useState(true);

  const query = useMemo(() => {
    const out: Record<string, string> = { range, mode, traffic };
    if (application) out.application = application;
    if (mode === 'release' && release) out.release = release;
    return out;
  }, [range, mode, traffic, application, release]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      setPending(true);
      void listViews(query)
        .then((next) => {
          if (!isCancelled()) setPage(next);
        })
        .catch(() => {
          if (!isCancelled()) setPage(null);
        })
        .finally(() => {
          if (!isCancelled()) setPending(false);
        });
    },
    [listViews, query],
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

  const rows = page?.rows || [];
  const filteredRows = useMemo(() => {
    const needle = routeQuery.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((r) => {
      const key = String(r.key || '').toLowerCase();
      const route = String(r.route || '').toLowerCase();
      const releaseName = String(r.release || '').toLowerCase();
      return key.includes(needle) || route.includes(needle) || releaseName.includes(needle);
    });
  }, [rows, routeQuery]);
  const sorted = useMemo(() => sortRows(filteredRows, sort), [filteredRows, sort]);
  const table = useRumClientPager(sorted, `${range}|${application}|${mode}|${release}|${sort}|${routeQuery}|${traffic}`);
  const summary = page?.summary || { lcpP75: 0, inpP75: 0, clsP75: 0 };
  const degrade = degradationReason(page);

  function SortHead({ label, k }: { label: string; k: SortKey }) {
    const active = sort === k;
    return (
      <button
        type="button"
        className={`inline-flex items-center gap-1 ${
          active ? 'text-[var(--color-text-1)]' : 'text-[var(--color-text-3)]'
        }`}
        onClick={() => setSort(k)}
      >
        {label}
        {active ? <CaretDownOutlined className="text-[10px]" /> : <SwapOutlined className="text-[10px] opacity-50" />}
      </button>
    );
  }

  const routeColumns: TableColumnsType<RumViewAggregateRow> = [
    {
      title: t('rum.views.route', '路由'),
      key: 'route',
      ellipsis: true,
      render: (_, r) => {
        const cause = rootCauseTone(r);
        return (
          <div className="flex min-w-0 items-center gap-2">
            <code
              className="truncate font-medium text-[var(--color-text-1)] transition-colors group-hover:text-[var(--color-primary)] group-hover:underline"
              title={r.key}
            >
              {r.key}
            </code>
            {cause.tone !== 'success' ? (
              <SemanticBadge
                label={t(`rum.views.rootCause.${cause.labelKey}`)}
                {...toneSemanticPalette(
                  cause.tone === 'danger' ? 'danger' : cause.tone === 'warning' ? 'warning' : 'neutral',
                )}
              />
            ) : null}
          </div>
        );
      },
    },
    {
      title: t('rum.views.dist.label', 'CWV 分布'),
      key: 'dist',
      width: 140,
      render: (_, r) => <DistributionBar dist={r.dist} />,
    },
    {
      title: t('rum.analytics.kpiViews', '浏览'),
      key: 'views',
      width: 72,
      render: (_, r) => <span className="tabular-nums">{r.views}</span>,
    },
    {
      title: t('rum.analytics.kpiSessions', '会话'),
      key: 'sessions',
      width: 72,
      render: (_, r) => <span className="tabular-nums">{r.sessions}</span>,
    },
    {
      title: <SortHead k="lcp" label="LCP P75" />,
      key: 'lcp',
      width: 96,
      render: (_, r) => (
        <span className={`font-mono tabular-nums ${toneTextClass(cwvTone('lcp', r.lcpP75))}`}>
          {formatMs(r.lcpP75)}
        </span>
      ),
    },
    {
      title: <SortHead k="inp" label="INP P75" />,
      key: 'inp',
      width: 96,
      render: (_, r) => (
        <span className={`font-mono tabular-nums ${toneTextClass(cwvTone('inp', r.inpP75))}`}>
          {formatMs(r.inpP75)}
        </span>
      ),
    },
    {
      title: <SortHead k="cls" label="CLS P75" />,
      key: 'cls',
      width: 88,
      render: (_, r) => (
        <span className={`font-mono tabular-nums ${toneTextClass(cwvTone('cls', r.clsP75))}`}>
          {r.clsP75 > 0 ? Number(r.clsP75).toFixed(3) : '—'}
        </span>
      ),
    },
    {
      title: t('rum.views.mom.viewsDelta', '走势'),
      key: 'mom',
      width: 96,
      render: (_, r) => <MomCell mom={r.mom} />,
    },
    {
      title: t('rum.views.device.label', '终端占比'),
      key: 'device',
      width: 120,
      render: (_, r) => <DeviceMixCell mix={r.deviceMix} />,
    },
  ];

  const releaseColumns: TableColumnsType<RumViewAggregateRow> = [
    {
      title: t('rum.views.release', '发布版本'),
      key: 'release',
      width: 180,
      render: (_, r) => <code className="truncate font-mono">{r.release || r.key}</code>,
    },
    {
      title: t('rum.views.route', '路由'),
      key: 'route',
      ellipsis: true,
      render: (_, r) => (
        <span className="truncate" title={r.route}>
          {r.route || '—'}
        </span>
      ),
    },
    {
      title: t('rum.analytics.kpiViews', '浏览'),
      key: 'views',
      width: 88,
      render: (_, r) => <span className="tabular-nums">{r.views}</span>,
    },
    {
      title: t('rum.analytics.kpiSessions', '会话'),
      key: 'sessions',
      width: 88,
      render: (_, r) => <span className="tabular-nums">{r.sessions}</span>,
    },
    {
      title: <SortHead k="lcp" label="LCP P75" />,
      key: 'lcp',
      width: 104,
      render: (_, r) => (
        <span className={`font-mono tabular-nums ${toneTextClass(cwvTone('lcp', r.lcpP75))}`}>
          {formatMs(r.lcpP75)}
        </span>
      ),
    },
    {
      title: <SortHead k="inp" label="INP P75" />,
      key: 'inp',
      width: 104,
      render: (_, r) => (
        <span className={`font-mono tabular-nums ${toneTextClass(cwvTone('inp', r.inpP75))}`}>
          {formatMs(r.inpP75)}
        </span>
      ),
    },
    {
      title: <SortHead k="cls" label="CLS P75" />,
      key: 'cls',
      width: 96,
      render: (_, r) => (
        <span className={`font-mono tabular-nums ${toneTextClass(cwvTone('cls', r.clsP75))}`}>
          {r.clsP75 > 0 ? Number(r.clsP75).toFixed(3) : '—'}
        </span>
      ),
    },
  ];

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t('rum.views.title', '视图与性能')}</h1>

      {degrade ? <div className="mb-2 shrink-0"><PipelineDegradedBanner reason={degrade} /></div> : null}

      <RumDualWorkbench
        asideTitle={t('rum.views.dimensionTitle', '视图维度')}
        aside={
          <>
            <RumFilterBlock title={t('rum.views.aggregate', '聚合')}>
              <Segmented
                block
                size="small"
                value={mode}
                onChange={(value) => setParams({ mode: String(value), release: null })}
                options={[
                  { value: 'route', label: t('rum.views.mode.route', '按路由') },
                  { value: 'release', label: t('rum.views.mode.release', '按版本') },
                ]}
              />
            </RumFilterBlock>
            <RumFilterBlock title={t('rum.common.timeWindow', '时间')}>
              <RumRangeSegmented block size="small" value={range} loading={pending} onChange={setRange} />
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
            {mode === 'release' ? (
              <RumFilterBlock title={t('rum.views.release', '发布版本')}>
                <Select
                  allowClear
                  size="small"
                  className="w-full"
                  placeholder={t('rum.views.allReleases', '全部版本')}
                  value={release || undefined}
                  onChange={(value) => setParams({ release: value || null })}
                  options={(page?.releases || []).map((item) => ({ value: item, label: item }))}
                />
              </RumFilterBlock>
            ) : null}
            <RumFilterBlock title={t('rum.traffic.label', '流量')}>
              <TrafficScopeControl block size="small" />
            </RumFilterBlock>
          </>
        }
        mainTitle={
          mode === 'release'
            ? t('rum.views.releaseDetail', '版本明细')
            : t('rum.views.routeDetail', '路由明细')
        }
        mainExtra={
          page ? (
            <>
              {(
                [
                  ['lcp', summary.lcpP75, formatMs(summary.lcpP75)],
                  ['inp', summary.inpP75, formatMs(summary.inpP75)],
                  [
                    'cls',
                    summary.clsP75,
                    summary.clsP75 > 0 ? Number(summary.clsP75).toFixed(3) : '—',
                  ],
                ] as const
              ).map(([metric, value, label]) => {
                const active = sort === metric;
                return (
                  <button
                    key={metric}
                    type="button"
                    className={`inline-flex items-baseline gap-1 rounded-md px-1.5 py-0.5 tabular-nums transition-colors ${
                      active ? 'bg-[var(--color-fill-2)]' : 'hover:bg-[var(--color-fill-1)]'
                    }`}
                    onClick={() => setSort(metric)}
                    title={t('rum.views.sortByMetric', '按 {metric} 排序', {
                      metric: metric.toUpperCase(),
                    })}
                  >
                    <span className={`font-mono text-[13px] font-semibold ${toneTextClass(cwvTone(metric, value))}`}>
                      {label}
                    </span>
                    <span className="text-[11px] text-[var(--color-text-3)]">
                      {t(`rum.views.cwv.${metric}`, metric.toUpperCase())}
                    </span>
                  </button>
                );
              })}
              <span className="tabular-nums text-[var(--color-text-3)]">
                {t('rum.views.rowCount', '{n} 条', { n: sorted.length })}
              </span>
            </>
          ) : null
        }
        main={
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
            <div className="flex h-8 shrink-0 flex-wrap items-center justify-end gap-2">
              <Input
                allowClear
                className="!h-8 w-60 !items-center !py-0"
                placeholder={t('rum.views.searchPlaceholder', '搜索路由')}
                prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
                value={routeQuery}
                onChange={(e) => setRouteQuery(e.target.value)}
              />
              <ExportButton
                rows={sorted as unknown as Record<string, unknown>[]}
                filename="rum-views"
              />
            </div>

            {pending ? (
              <RumTableSkeleton
                size="middle"
                columns={rumSkeletonColumns(mode === 'release' ? releaseColumns : routeColumns)}
              />
            ) : sorted.length === 0 ? (
              <div className="flex min-h-0 flex-1 items-center justify-center">
                <Empty
                  description={
                    <div>
                      <p className="m-0 text-sm font-semibold">{t('rum.views.empty', '没有视图样本')}</p>
                      <p className="mt-1 text-xs text-[var(--color-text-3)]">
                        {t('rum.views.emptyHint', '选择应用与时间范围后再试。')}
                      </p>
                    </div>
                  }
                />
              </div>
            ) : sorted.length > 0 ? (
              <div className="min-h-0 min-w-0 flex-1">
                <CustomTable<RumViewAggregateRow>
                  rowKey="key"
                  dataSource={table.rows}
                  pagination={{
                    current: table.pagination.current,
                    pageSize: table.pagination.pageSize,
                    total: table.pagination.total,
                    showSizeChanger: table.pagination.showSizeChanger,
                    onChange: table.pagination.onChange,
                  }}
                  tableLayout="fixed"
                  size="middle"
                  autoScrollX={false}
                  columns={mode === 'release' ? releaseColumns : routeColumns}
                  onRow={(r) => ({
                    onClick: () => {
                      if (mode === 'release') {
                        router.push(
                          `/rum/releases?application=${encodeURIComponent(application)}&range=${range}`,
                        );
                      } else {
                        router.push(
                          `/rum/sessions?range=${range}&route=${encodeURIComponent(r.key)}${
                            application ? `&application=${encodeURIComponent(application)}` : ''
                          }`,
                        );
                      }
                    },
                    className: 'group cursor-pointer transition-colors hover:bg-[var(--color-fill-2)]',
                  })}
                />
              </div>
            ) : null}
          </div>
        }
      />
    </div>
  );
}
