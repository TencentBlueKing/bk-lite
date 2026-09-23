'use client';

import { useCallback, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  BranchesOutlined,
  ClockCircleOutlined,
  CloudServerOutlined,
  GlobalOutlined,
  LaptopOutlined,
  RightOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { Button, Empty, type TableColumnsType } from 'antd';

import {
  useRumQueries,
  type RumApplicationOverview,
  type RumOverviewDistribution,
  type RumSessionRow,
} from '@/app/rum/api';
import DistributionList from '@/app/rum/applications/ui/distribution-list';
import { OverviewKpi } from '@/app/rum/applications/ui/overview-kpi';
import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import { RumDetailTitle } from '@/app/rum/components/rum-back-button';
import RumListToolbar from '@/app/rum/components/rum-list-toolbar';
import RumRangeSegmented from '@/app/rum/components/rum-range-segmented';
import RumRefreshButton from '@/app/rum/components/rum-refresh-button';
import { RumOverviewSkeleton, RumTableSkeleton, rumSkeletonColumns } from '@/app/rum/components/rum-skeleton';
import { degradationReason } from '@/app/rum/lib/degradation';
import { displayRoute, truncateMiddle } from '@/app/rum/lib/format';
import { rumSetupPath } from '@/app/rum/lib/ingest';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import SessionTrendChart from '@/app/rum/sessions/ui/session-trend-chart';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';

export default function ApplicationOverviewPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useParams<{ name: string }>();
  const name = decodeURIComponent(params.name || '');
  const { range, setRange } = useRumSearchParams();
  const { getApplicationOverview, listSessions, authReady } = useRumQueries();

  const [overview, setOverview] = useState<RumApplicationOverview | null>(null);
  const [recent, setRecent] = useState<RumSessionRow[]>([]);
  const [pending, setPending] = useState(true);
  const [recentPending, setRecentPending] = useState(true);

  const load = useCallback(async () => {
    if (!name) return;
    setPending(true);
    try {
      setOverview(await getApplicationOverview(name, range));
    } catch {
      setOverview(null);
    } finally {
      setPending(false);
    }
  }, [getApplicationOverview, name, range]);

  const loadRecent = useCallback(async () => {
    if (!name) return;
    setRecentPending(true);
    try {
      const data = await listSessions({
        application: name,
        range,
        orderBy: 'start',
        limit: '8',
        traffic: 'all',
      });
      setRecent(data.sessions);
    } catch {
      setRecent([]);
    } finally {
      setRecentPending(false);
    }
  }, [listSessions, name, range]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      if (!name) return;
      setPending(true);
      void getApplicationOverview(name, range)
        .then((next) => {
          if (!isCancelled()) setOverview(next);
        })
        .catch(() => {
          if (!isCancelled()) setOverview(null);
        })
        .finally(() => {
          if (!isCancelled()) setPending(false);
        });
    },
    [getApplicationOverview, name, range],
  );

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      if (!name) return;
      setRecentPending(true);
      void listSessions({
        application: name,
        range,
        orderBy: 'start',
        limit: '8',
        traffic: 'all',
      })
        .then((data) => {
          if (!isCancelled()) setRecent(data.sessions);
        })
        .catch(() => {
          if (!isCancelled()) setRecent([]);
        })
        .finally(() => {
          if (!isCancelled()) setRecentPending(false);
        });
    },
    [listSessions, name, range],
  );

  const degrade = degradationReason(overview);
  const kpi = overview?.kpi || null;
  const scope = `application=${encodeURIComponent(name)}&range=${range}`;

  const countryRows: RumOverviewDistribution[] = (overview?.countries || []).map((row) => ({
    key: row.country || t('rum.overview.unknown', '(未知)'),
    sessions: row.sessions,
    views: row.views,
  }));
  const countrySessions = countryRows.reduce((sum, r) => sum + r.sessions, 0);

  const deviceTotal = (overview?.devices.mobile || 0) + (overview?.devices.desktop || 0);
  const deviceRows: RumOverviewDistribution[] =
    overview && deviceTotal > 0
      ? [
        {
          key: t('rum.overview.devicesMobile', '移动端'),
          sessions: overview.devices.mobile,
          views: 0,
        },
        {
          key: t('rum.overview.devicesDesktop', '桌面端'),
          sessions: overview.devices.desktop,
          views: 0,
        },
      ]
      : [];
  const deviceSessions = deviceTotal;

  const envSessions = (overview?.environments || []).reduce((sum, r) => sum + r.sessions, 0);
  const releaseSessions = (overview?.releases || []).reduce((sum, r) => sum + r.sessions, 0);

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-y-auto">
      <RumListToolbar
        leading={
          <RumDetailTitle title={name} onBack={() => router.push('/rum/applications')} />
        }
        trailing={
          <>
            <RumRangeSegmented value={range} loading={pending} onChange={setRange} />
            <Button
              icon={<SettingOutlined />}
              onClick={() => router.push(rumSetupPath(name))}
            >
              {t('rum.overview.setup', '接入配置')}
            </Button>
            <RumRefreshButton
              loading={pending}
              onClick={() => {
                void load();
                void loadRecent();
              }}
            />
          </>
        }
      />

      {degrade ? <PipelineDegradedBanner reason={degrade} /> : null}

      {pending ? <RumOverviewSkeleton /> : null}

      {!pending && !overview ? (
        <Empty description={t('rum.detail.missing', '无法加载该应用')} />
      ) : null}

      {!pending && overview && kpi ? (
        <div className="flex min-w-0 flex-col gap-4">
          {/* 6 列核心指标卡 */}
          <OverviewKpi
            row={kpi}
            onOpenSessions={() => router.push(`/rum/sessions?${scope}`)}
            onOpenViews={() => router.push(`/rum/views?${scope}`)}
            onOpenErrors={() => router.push(`/rum/errors?${scope}`)}
          />

          {/* 会话趋势卡片 */}
          <SessionTrendChart points={overview.trend} asCard />

          {/* 4 个分布板块：统一卡片化 */}
          <div className="grid min-w-0 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <DistributionCard
              title={t('rum.overview.countries', '国家 / 地区')}
              icon={<GlobalOutlined className="text-sm text-sky-500" />}
              total={countrySessions}
              badgeClass="bg-sky-500/10 text-sky-600 dark:text-sky-400"
            >
              <DistributionList
                rows={countryRows}
                strokeColor="#0ea5e9"
                hoverTextClass="group-hover/dist:text-sky-600"
              />
            </DistributionCard>

            <DistributionCard
              title={t('rum.overview.devices', '设备')}
              icon={<LaptopOutlined className="text-sm text-indigo-500" />}
              total={deviceSessions}
              badgeClass="bg-indigo-500/10 text-indigo-600 dark:text-indigo-400"
            >
              <DistributionList
                rows={deviceRows}
                strokeColor="#6366f1"
                hoverTextClass="group-hover/dist:text-indigo-600"
              />
            </DistributionCard>

            <DistributionCard
              title={t('rum.overview.environments', '环境')}
              icon={<CloudServerOutlined className="text-sm text-emerald-500" />}
              total={envSessions}
              badgeClass="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
            >
              <DistributionList
                rows={overview.environments}
                strokeColor="#10b981"
                hoverTextClass="group-hover/dist:text-emerald-600"
              />
            </DistributionCard>

            <DistributionCard
              title={t('rum.overview.releases', '版本')}
              icon={<BranchesOutlined className="text-sm text-amber-500" />}
              total={releaseSessions}
              badgeClass="bg-amber-500/10 text-amber-700 dark:text-amber-400"
            >
              <DistributionList
                rows={overview.releases}
                strokeColor="#f59e0b"
                hoverTextClass="group-hover/dist:text-amber-600"
              />
            </DistributionCard>
          </div>

          {/* 近期会话卡片 */}
          <section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
              <div className="flex items-center gap-2">
                <ClockCircleOutlined className="text-sm text-[var(--color-primary)]" />
                <h2 className="m-0 text-[13px] font-semibold text-[var(--color-text-1)]">
                  {t('rum.overview.recent', '近期会话')}
                </h2>
                {recent.length > 0 ? (
                  <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] px-1.5 text-xs font-semibold tabular-nums text-[var(--color-primary)]">
                    {recent.length}
                  </span>
                ) : null}
              </div>
              <Link
                href={`/rum/sessions?${scope}`}
                className="inline-flex items-center gap-1 text-xs text-[var(--color-text-3)] transition-colors hover:text-[var(--color-primary)]"
              >
                <span>{t('rum.overview.viewAll', '查看全部')}</span>
                <RightOutlined className="text-[10px]" />
              </Link>
            </div>
            <RecentSessions sessions={recent} range={range} loading={recentPending} />
          </section>
        </div>
      ) : null}
    </div>
  );
}

function DistributionCard({
  title,
  icon,
  total,
  badgeClass,
  children,
}: {
  title: string;
  icon?: ReactNode;
  total?: number;
  badgeClass?: string;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
      <div className="flex items-center justify-between border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
        <div className="flex items-center gap-2">
          {icon}
          <h2 className="m-0 text-[13px] font-semibold text-[var(--color-text-1)]">{title}</h2>
          {total != null && total > 0 ? (
            <span
              className={[
                'inline-flex h-5 min-w-[20px] items-center justify-center rounded-full px-1.5 text-xs font-semibold tabular-nums',
                badgeClass,
              ]
                .filter(Boolean)
                .join(' ')}
            >
              {total}
            </span>
          ) : null}
        </div>
      </div>
      <div className="p-3.5">{children}</div>
    </section>
  );
}

function RecentSessions({
  sessions,
  range,
  loading,
}: {
  sessions: RumSessionRow[];
  range: string;
  loading?: boolean;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const columns: TableColumnsType<RumSessionRow> = [
    {
      title: t('rum.sessions.session', '会话'),
      dataIndex: 'sessionId',
      key: 'sessionId',
      width: '22%',
      render: (value: string) => (
        <code className="font-mono text-xs text-[var(--color-primary)] transition-colors hover:underline" title={value}>
          {truncateMiddle(value, 20)}
        </code>
      ),
    },
    {
      title: t('rum.sessions.started', '开始时间'),
      dataIndex: 'startTime',
      key: 'startTime',
      width: '18%',
      render: (value?: string) => (
        <span className="text-xs tabular-nums text-[var(--color-text-2)]">
          {value
            ? new Date(value).toLocaleString(undefined, {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })
            : '—'}
        </span>
      ),
    },
    {
      title: t('rum.overview.countryViews', '浏览'),
      dataIndex: 'viewCount',
      key: 'viewCount',
      width: '12%',
      render: (value?: number) => <span className="text-xs tabular-nums text-[var(--color-text-2)]">{value ?? 0}</span>,
    },
    {
      title: t('rum.sessions.errored', '出错'),
      dataIndex: 'errorCount',
      key: 'errorCount',
      width: '12%',
      render: (value?: number) => (
        <span className={`text-xs tabular-nums ${value ? 'font-medium text-[var(--color-fail)]' : 'text-[var(--color-text-3)]'}`}>
          {value ?? 0}
        </span>
      ),
    },
    {
      title: t('rum.overview.country', '国家/地区'),
      dataIndex: 'geoCountry',
      key: 'geoCountry',
      width: '14%',
      render: (value?: string) => (
        <span className="text-xs text-[var(--color-text-2)]">{value || '—'}</span>
      ),
    },
    {
      title: t('rum.sessions.landing', '落地页'),
      dataIndex: 'entryRoute',
      key: 'entryRoute',
      render: (value?: string) => {
        const route = displayRoute(value);
        return (
          <span className="truncate font-mono text-xs text-[var(--color-text-2)]" title={value || undefined}>
            {route || '—'}
          </span>
        );
      },
    },
  ];

  if (loading && sessions.length === 0) {
    return <RumTableSkeleton size="middle" rows={6} columns={rumSkeletonColumns(columns)} />;
  }

  return (
    <CustomTable<RumSessionRow>
      rowKey="sessionId"
      size="middle"
      pagination={false}
      tableLayout="fixed"
      dataSource={sessions}
      columns={columns}
      locale={{ emptyText: t('rum.overview.recentEmpty', '当前窗口暂无会话') }}
      onRow={(session) => ({
        onClick: () =>
          router.push(
            `/rum/sessions/${encodeURIComponent(session.sessionId)}?application=${encodeURIComponent(session.application)}&range=${range}`,
          ),
        className: 'cursor-pointer transition-colors hover:bg-[var(--color-fill-2)]',
      })}
    />
  );
}
