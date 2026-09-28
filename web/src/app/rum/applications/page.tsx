'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  GlobalOutlined,
  PlusOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  Button,
  Empty,
  Input,
  Select,
  Tag,
  Tooltip,
  type TableColumnsType,
} from 'antd';

import {
  useRumQueries,
  type RumApplicationHealthItem,
  type RumApplicationsCatalog,
} from '@/app/rum/api';
import CreateApplicationDrawer from '@/app/rum/applications/ui/create-application-drawer';
import { CatalogKpi } from '@/app/rum/applications/ui/overview-kpi';
import RumIconAction from '@/app/rum/components/rum-icon-action';
import RumListToolbar from '@/app/rum/components/rum-list-toolbar';
import { RumSingleWorkbench } from '@/app/rum/components/rum-dual-workbench';
import RumPageError from '@/app/rum/components/rum-page-error';
import RumPermission from '@/app/rum/components/rum-permission';
import RumRangeSegmented from '@/app/rum/components/rum-range-segmented';
import RumRefreshButton from '@/app/rum/components/rum-refresh-button';
import { RumKpiSkeleton, RumTableSkeleton, rumSkeletonColumns } from '@/app/rum/components/rum-skeleton';
import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import Sparkline from '@/app/apm/components/home/sparkline';
import {
  appExperienceTone,
  CWV_THRESHOLDS,
  cwvTone,
  errorRateTone,
  formatPct,
  toneColor,
  toneDotClass,
  toneSemanticPalette,
  toneTextClass,
  type CwvTone,
} from '@/app/rum/lib/cwv';
import SemanticBadge from '@/components/semantic-badge';
import { degradationReason } from '@/app/rum/lib/degradation';
import { resolveRumPageState } from '@/app/rum/lib/page-state';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import { useRumClientPager } from '@/app/rum/lib/table-pagination';
import CustomTable from '@/components/custom-table';
import { useLocale } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';

type SortKey = 'health' | 'sessions' | 'errorRate';

const HEALTH_ORDER: Record<CwvTone, number> = { danger: 0, warning: 1, success: 2, neutral: 3 };

function relativeLastSeen(ms0: number, nowMs: number, locale: string): string {
  if (!ms0) return '—';
  const diffSec = Math.round((ms0 - nowMs) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const abs = Math.abs(diffSec);
  if (abs < 60) return rtf.format(diffSec, 'second');
  if (abs < 3600) return rtf.format(Math.round(diffSec / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), 'hour');
  return rtf.format(Math.round(diffSec / 86400), 'day');
}

function CwvValue({ value, metric }: { value: number; metric: 'lcp' | 'inp' }) {
  const tone = cwvTone(metric, value);
  const gap = value > 0 ? value - CWV_THRESHOLDS[metric][0] : 0;
  const gapLabel = gap > 0 ? `+${Math.round(gap)}ms` : '';
  return (
    <div className="flex flex-col items-start gap-0.5">
      <span className={`font-mono tabular-nums ${toneTextClass(tone)}`}>
        {value > 0 ? `${Math.round(value)}ms` : '—'}
      </span>
      {gapLabel ? (
        <span className="text-[11px] leading-tight text-[var(--theme-color-status-warning)]">{gapLabel}</span>
      ) : null}
    </div>
  );
}

export default function RumApplicationsPage() {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const router = useRouter();
  const { range, setRange } = useRumSearchParams();
  const { getAnalyticsCatalog, authReady } = useRumQueries();
  const [createOpen, setCreateOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortKey>('health');
  const [page, setPage] = useState<RumApplicationsCatalog | null>(null);
  const [pending, setPending] = useState(true);

  const load = useCallback(async () => {
    setPending(true);
    try {
      setPage(await getAnalyticsCatalog(range));
    } catch {
      setPage(null);
    } finally {
      setPending(false);
    }
  }, [getAnalyticsCatalog, range]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      setPending(true);
      void getAnalyticsCatalog(range)
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
    [getAnalyticsCatalog, range],
  );

  const applications = page?.applications || [];
  const renderNow = Date.now();
  const degrade = degradationReason(page);
  const chrome = resolveRumPageState({
    pending,
    error: !pending && page === null ? t('rum.applications.loadFailed', '应用列表加载失败') : null,
    itemCount: applications.length,
    page,
  });

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const filtered = needle
      ? applications.filter((a) => a.application.toLowerCase().includes(needle))
      : applications;
    return [...filtered].sort((a, b) => {
      if (sort === 'sessions') return b.sessions - a.sessions;
      if (sort === 'errorRate') return b.errorRate - a.errorRate;
      const ha = a.enabled ? appExperienceTone(a.lcpP75, a.inpP75, a.errorRate) : 'neutral';
      const hb = b.enabled ? appExperienceTone(b.lcpP75, b.inpP75, b.errorRate) : 'neutral';
      const d = HEALTH_ORDER[ha] - HEALTH_ORDER[hb];
      return d !== 0 ? d : b.sessions - a.sessions;
    });
  }, [applications, search, sort]);
  const table = useRumClientPager(visible, `${range}|${search}|${sort}`);

  function healthTone(a: RumApplicationHealthItem): CwvTone {
    return a.enabled ? appExperienceTone(a.lcpP75, a.inpP75, a.errorRate) : 'neutral';
  }

  function healthLabel(a: RumApplicationHealthItem): string {
    if (a.enabled && a.sessions > 0 && a.sessions < 5) {
      return t('rum.applications.healthObserving', '观察中');
    }
    return t(`rum.analytics.health.${healthTone(a)}`);
  }

  function overviewHref(a: RumApplicationHealthItem): string {
    return `/rum/applications/${encodeURIComponent(a.application)}/overview?range=${range}`;
  }

  const columns: TableColumnsType<RumApplicationHealthItem> = [
    {
      title: t('rum.applications.application', '应用'),
      key: 'application',
      ellipsis: true,
      render: (_, app) => {
        const hTone = healthTone(app);
        return (
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="inline-flex min-w-0 items-center gap-2">
              <span className={`size-2 shrink-0 rounded-full ${toneDotClass(hTone)}`} aria-hidden />
              <Link
                href={overviewHref(app)}
                className="truncate font-medium text-[var(--color-text-1)] transition-colors hover:text-[var(--color-primary)] hover:underline"
                onClick={(e) => e.stopPropagation()}
              >
                {app.application}
              </Link>
              {!app.enabled ? (
                <span className="shrink-0 text-[10px] text-[var(--color-text-3)]">
                  {t('rum.common.disabled', '已禁用')}
                </span>
              ) : null}
              {app.sessions === 0 ? (
                <Tag bordered={false} className="m-0 shrink-0 text-[10px] leading-4 text-[var(--color-text-3)]">
                  {t('rum.applications.noDataInWindow', '窗口内无数据')}
                </Tag>
              ) : null}
            </span>
            <span className="truncate text-xs tabular-nums text-[var(--color-text-3)]">
              {t('rum.applications.subline', '{errors} 错误 · {views} 浏览 · {lastSeen}', {
                errors: app.errors,
                views: app.views,
                lastSeen: relativeLastSeen(app.lastSeenMs || 0, renderNow, locale),
              })}
            </span>
          </div>
        );
      },
    },
    {
      title: t('rum.applications.collectionMetadata', 'SDK'),
      key: 'metadata',
      width: 176,
      render: (_, app) => {
        if (!app.sdkVersion && !app.environment && !app.release) {
          return (
            <span className="text-[var(--color-text-3)]">
              {t('rum.applications.waitingForTelemetry', '未接入')}
            </span>
          );
        }
        return (
          <div className="flex min-w-0 flex-col gap-0.5 leading-snug">
            <span className="truncate">
              {t('rum.applications.faroSdk', 'Faro SDK')}{' '}
              <span className="font-mono">
                {app.sdkVersion || t('rum.applications.metadataNotReported', '未上报')}
              </span>
            </span>
            <span className="truncate text-xs text-[var(--color-text-3)]">
              {app.environment || t('rum.applications.metadataNotReported', '未上报')} ·{' '}
              {app.release || t('rum.applications.metadataNotReported', '未上报')}
            </span>
          </div>
        );
      },
    },
    {
      title: t('rum.applications.health', '体验健康'),
      key: 'health',
      width: 104,
      render: (_, app) => (
        <SemanticBadge label={healthLabel(app)} {...toneSemanticPalette(healthTone(app))} />
      ),
    },
    {
      title: t('rum.applications.trendV2', '浏览趋势'),
      key: 'trend',
      width: 148,
      render: (_, app) => {
        const spark = page?.sparklines?.[app.application] || [];
        return spark.length ? (
          <Sparkline
            data={spark}
            width={132}
            height={28}
            color={toneColor(healthTone(app))}
            fit="fixed"
            kind="area"
          />
        ) : (
          <span className="text-[var(--color-text-4)]">—</span>
        );
      },
    },
    {
      title: t('rum.applications.sessions', '会话'),
      key: 'sessions',
      width: 80,
      render: (_, app) => (
        <span className="font-mono tabular-nums">{app.sessions}</span>
      ),
    },
    {
      title: t('rum.applications.errorRate', '错误率'),
      key: 'errorRate',
      width: 96,
      render: (_, app) => {
        const eTone = errorRateTone(app.errorRate);
        return (
          <Tooltip title={t('rum.applications.errorRateHint', '错误率 = 出错会话 / 总会话')}>
            <span className={`font-mono tabular-nums ${toneTextClass(eTone)}`}>
              {formatPct(app.errorRate)}
            </span>
          </Tooltip>
        );
      },
    },
    {
      title: 'LCP P75',
      key: 'lcp',
      width: 128,
      render: (_, app) => <CwvValue value={app.lcpP75} metric="lcp" />,
    },
    {
      title: 'INP P75',
      key: 'inp',
      width: 112,
      render: (_, app) => <CwvValue value={app.inpP75} metric="inp" />,
    },
    {
      title: t('rum.common.actions', '操作'),
      key: 'actions',
      width: 80,
      fixed: 'right',
      onHeaderCell: () => ({ className: '!pr-6' }),
      onCell: () => ({ className: '!pr-6' }),
      render: (_, app) => (
        <div className="whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
          <RumIconAction
            title={t('rum.applications.openOverview', '总览')}
            onClick={() => router.push(overviewHref(app))}
          />
        </div>
      ),
    },
  ];

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t('rum.applications.title', '应用')}</h1>

      {degrade ? <div className="mb-2 shrink-0"><PipelineDegradedBanner reason={degrade} /></div> : null}

      <CreateApplicationDrawer open={createOpen} onOpenChange={setCreateOpen} />

      {chrome === 'loading' ? (
        <div className="mb-2 shrink-0">
          <RumKpiSkeleton />
        </div>
      ) : page && page.configured && !page.analyticsUnavailable && applications.length > 0 ? (
        <div className="mb-2 shrink-0">
          <CatalogKpi applications={applications} />
        </div>
      ) : null}

      <RumSingleWorkbench
        toolbar={
          <RumListToolbar
            spacing="flush"
            trailing={
              <>
                <RumRangeSegmented value={range} loading={pending} onChange={setRange} />
                <Select
                  value={sort}
                  onChange={(value) => setSort(value as SortKey)}
                  className="h-8 w-[120px] [&_.ant-select-selector]:!h-8 [&_.ant-select-selector]:!items-center"
                  options={[
                    { value: 'health', label: t('rum.applications.sortHealth', '按健康') },
                    { value: 'sessions', label: t('rum.applications.sortSessions', '按会话') },
                    { value: 'errorRate', label: t('rum.applications.sortErrorRate', '按错误率') },
                  ]}
                />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t('rum.applications.searchPlaceholder', '搜索应用…')}
                  prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
                  allowClear
                  className="!h-8 w-60 !items-center !py-0"
                />
                <RumRefreshButton loading={pending} onClick={() => void load()} />
                <RumPermission resource="applications" action="Operate">
                  <Button type="primary" icon={<PlusOutlined aria-hidden="true" />} onClick={() => setCreateOpen(true)}>
                    {t('common.new', '新建')}
                  </Button>
                </RumPermission>
              </>
            }
          />
        }
      >
        {chrome === 'loading' ? (
          <RumTableSkeleton columns={rumSkeletonColumns(columns)} />
        ) : chrome === 'error' ? (
          <div className="flex min-h-0 flex-1 items-center justify-center">
            <RumPageError
              message={t('rum.applications.loadFailed', '应用列表加载失败')}
              onRetry={() => void load()}
            />
          </div>
        ) : applications.length === 0 ? (
          <div className="flex min-h-0 flex-1 items-center justify-center">
            <Empty
              image={
                <span className="inline-flex size-11 items-center justify-center rounded-full bg-[var(--color-fill-2)] text-[var(--color-text-3)]">
                  <GlobalOutlined />
                </span>
              }
              description={
                <div className="mx-auto max-w-md">
                  {page?.controlUnavailable ? (
                    <>
                      <p className="m-0 text-sm font-semibold">
                        {t('rum.applications.controlUnavailableTitle', '控制面不可达')}
                      </p>
                      <p className="mt-1 text-xs text-[var(--color-text-3)]">
                        {t(
                          'rum.applications.controlUnavailableHint',
                          '无法读取应用列表与接入配置，请检查 RUM controller 连接。',
                        )}
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="m-0 text-sm font-semibold">
                        {t('rum.applications.empty', '还没有 RUM 应用')}
                      </p>
                      <p className="mt-1 text-xs text-[var(--color-text-3)]">
                        {t('rum.applications.emptyHint', '先创建一个应用，再配置 Origin 与 SDK。')}
                      </p>
                      <RumPermission resource="applications" action="Operate">
                        <div className="mt-4 flex justify-center">
                          <Button type="primary" icon={<PlusOutlined aria-hidden="true" />} onClick={() => setCreateOpen(true)}>
                            {t('common.new', '新建')}
                          </Button>
                        </div>
                      </RumPermission>
                    </>
                  )}
                </div>
              }
            />
          </div>
        ) : (
          <div className="min-h-0 min-w-0 flex-1">
            <CustomTable<RumApplicationHealthItem>
              rowKey="application"
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
              columns={columns}
              onRow={(app) => ({
                onClick: () => router.push(overviewHref(app)),
                className: 'cursor-pointer transition-colors hover:bg-[var(--color-fill-2)]',
              })}
            />
          </div>
        )}
      </RumSingleWorkbench>
    </div>
  );
}
