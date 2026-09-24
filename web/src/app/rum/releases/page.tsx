'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  EnvironmentOutlined,
  KeyOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Button, Empty, Popconfirm, Segmented, Select, Tooltip, type TableColumnsType } from 'antd';

import { useRumQueries, type RumReleasePage, type RumReleaseRow } from '@/app/rum/api';
import RumIconAction from '@/app/rum/components/rum-icon-action';
import RumListToolbar from '@/app/rum/components/rum-list-toolbar';
import { RumSingleWorkbench } from '@/app/rum/components/rum-dual-workbench';
import { RumMetricGrid } from '@/app/rum/components/rum-metric-card';
import RumPermission from '@/app/rum/components/rum-permission';
import RumRangeSegmented from '@/app/rum/components/rum-range-segmented';
import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import ExportButton from '@/app/rum/components/export-button';
import { RumKpiSkeleton, RumTableSkeleton, rumSkeletonColumns } from '@/app/rum/components/rum-skeleton';
import TrafficScopeControl from '@/app/rum/components/traffic-scope';
import { cwvTone, formatMs, toneSemanticPalette } from '@/app/rum/lib/cwv';
import { degradationReason } from '@/app/rum/lib/degradation';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import { useRumClientPager } from '@/app/rum/lib/table-pagination';
import SourceMapManager from '@/app/rum/releases/ui/sourcemap-manager';
import CustomTable from '@/components/custom-table';
import SemanticBadge from '@/components/semantic-badge';
import { useTranslation } from '@/utils/i18n';

function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function Delta({ value, suffix = '' }: { value?: number; suffix?: string }) {
  if (value == null || value === 0) return null;
  const up = value > 0;
  return (
    <span
      className={`ml-1.5 inline-flex items-center gap-0.5 text-[11px] font-normal tabular-nums ${
        up ? 'text-[var(--color-fail)]' : 'text-[var(--color-success)]'
      }`}
    >
      {up ? <ArrowUpOutlined className="text-[10px]" /> : <ArrowDownOutlined className="text-[10px]" />}
      {up ? '+' : ''}
      {value}
      {suffix}
    </span>
  );
}

export default function RumReleasesPage() {
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
  const { listReleases, putBaseline, listApplications, rotateSourceMapCredential, authReady } =
    useRumQueries();

  const isSourceMapTab =
    searchParams.get('tab') === 'sourcemaps' || searchParams.has('sourcemap');
  const tab = isSourceMapTab ? 'sourcemaps' : 'releases';

  const [page, setPage] = useState<RumReleasePage | null>(null);
  const [apps, setApps] = useState<string[]>([]);
  const [pending, setPending] = useState(true);
  const [settingBaseline, setSettingBaseline] = useState<string | null>(null);
  const [ciToken, setCiToken] = useState('');
  const [rotatingToken, setRotatingToken] = useState(false);

  const query = useMemo(() => {
    const out: Record<string, string> = { range, traffic };
    if (application) out.application = application;
    return out;
  }, [range, traffic, application]);

  const load = useCallback(async () => {
    setPending(true);
    try {
      setPage(await listReleases(query));
    } catch {
      setPage(null);
    } finally {
      setPending(false);
    }
  }, [listReleases, query]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      setPending(true);
      void listReleases(query)
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
    [listReleases, query],
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

  useEffect(() => {
    setCiToken('');
  }, [application, tab]);

  const rows = page?.releases || [];
  const table = useRumClientPager(rows, `${range}|${application}|${traffic}`);
  const degrade = degradationReason(page);
  const summary = useMemo(() => {
    let errorCount = 0;
    let newIssues = 0;
    let sessions = 0;
    let users = 0;
    for (const row of rows) {
      errorCount += row.errorCount || 0;
      newIssues += row.newIssues || 0;
      sessions += row.affectedSessions || 0;
      users += row.affectedUsers || 0;
    }
    return { versions: rows.length, errorCount, newIssues, sessions, users };
  }, [rows]);

  function setTab(nextTab: string) {
    if (nextTab === 'sourcemaps') {
      setParams({ tab: 'sourcemaps', sourcemap: null });
    } else {
      setParams({ tab: null, sourcemap: null });
    }
  }

  async function rotateCiToken() {
    if (!application) return;
    setRotatingToken(true);
    try {
      const result = await rotateSourceMapCredential(application);
      setCiToken(result.token);
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setRotatingToken(false);
    }
  }

  async function setBaseline(release: RumReleaseRow) {
    if (!application) return;
    setSettingBaseline(release.release);
    try {
      await putBaseline(application, release.release);
      await load();
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setSettingBaseline(null);
    }
  }

  function experience(release: RumReleaseRow): {
    label: string;
    tone: 'success' | 'warning' | 'danger' | 'neutral';
    detail: string;
  } {
    if (release.newIssues > 0) {
      return {
        label: t('rum.releases.experienceEvidence.newIssues', '新增 {n} 个问题', {
          n: release.newIssues,
        }),
        tone: 'danger',
        detail: '',
      };
    }
    if (release.suspectedRegression) {
      if (release.lcpP75Delta && release.lcpP75Delta > 0) {
        return {
          label: t('rum.releases.experienceEvidence.lcpDegrade', 'LCP {v}', {
            v: formatMs(release.lcpP75),
          }),
          tone: 'danger',
          detail: `+${Math.round(release.lcpP75Delta)}ms`,
        };
      }
      return {
        label: t('rum.releases.experienceEvidence.noDegrade', '未见体验退化'),
        tone: 'warning',
        detail: '',
      };
    }
    const lcp = cwvTone('lcp', release.lcpP75 || 0);
    if ((lcp === 'danger' || lcp === 'warning') && (release.lcpP75 || 0) > 0) {
      return {
        label: t('rum.releases.experienceEvidence.lcpDegrade', 'LCP {v}', {
          v: formatMs(release.lcpP75),
        }),
        tone: lcp,
        detail: '',
      };
    }
    return {
      label: t('rum.releases.experienceEvidence.noDegrade', '未见体验退化'),
      tone: 'success',
      detail: '',
    };
  }

  function errorsHref(release: string) {
    const next = new URLSearchParams({ range, release });
    if (application) next.set('application', application);
    return `/rum/errors?${next}`;
  }

  const columns = useMemo<TableColumnsType<RumReleaseRow>>(
    () => [
      {
        title: t('rum.views.release', '发布版本'),
        key: 'release',
        ellipsis: true,
        render: (_: unknown, r: RumReleaseRow) => (
          <span className="flex items-center gap-1.5 font-mono">
            <span>{r.release}</span>
            {r.isBaseline ? (
              <span className="inline-flex shrink-0 items-center gap-0.5 rounded-sm bg-[var(--color-primary-bg)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-primary)]">
                <EnvironmentOutlined className="text-[10px]" />
                {t('rum.releases.baseline', '基线')}
              </span>
            ) : null}
          </span>
        ),
      },
      {
        title: t('rum.releases.experience', '体验证据'),
        key: 'experience',
        width: 176,
        render: (_: unknown, r: RumReleaseRow) => {
          const exp = experience(r);
          return (
            <span className="inline-flex items-center gap-1" title={exp.detail || undefined}>
              <SemanticBadge
                label={
                  <span className="inline-flex items-center gap-1">
                    {exp.tone === 'danger' ? <WarningOutlined className="shrink-0 text-[11px]" /> : null}
                    <span>{exp.label}</span>
                  </span>
                }
                {...toneSemanticPalette(exp.tone)}
              />
            </span>
          );
        },
      },
      {
        title: t('rum.releases.deployedAt', '首次出现'),
        key: 'firstSeen',
        width: 136,
        render: (_: unknown, r: RumReleaseRow) => (
          <span className="tabular-nums">{formatWhen(r.firstSeen)}</span>
        ),
      },
      {
        title: t('rum.errors.title', '错误追踪'),
        key: 'errorCount',
        width: 96,
        render: (_: unknown, r: RumReleaseRow) => (
          <span className="font-mono tabular-nums">
            <span className={r.errorCount > 0 ? 'text-[var(--color-fail)]' : ''}>
              {r.errorCount}
            </span>
            <Delta value={r.errorDelta} />
          </span>
        ),
      },
      {
        title: t('rum.releases.newIssues', '新增问题'),
        key: 'newIssues',
        width: 88,
        render: (_: unknown, r: RumReleaseRow) => (
          <span
            className={`font-mono tabular-nums ${
              r.newIssues > 0 ? 'text-[var(--color-fail)]' : ''
            }`}
          >
            {r.newIssues}
          </span>
        ),
      },
      {
        title: t('rum.errors.detail.affectedSessions', '影响会话'),
        key: 'affectedSessions',
        width: 88,
        render: (_: unknown, r: RumReleaseRow) => (
          <span className="font-mono tabular-nums">
            <span>{r.affectedSessions}</span>
            <Delta value={r.sessionsDelta} />
          </span>
        ),
      },
      {
        title: t('rum.errors.detail.affectedUsers', '影响用户'),
        key: 'affectedUsers',
        width: 88,
        render: (_: unknown, r: RumReleaseRow) => (
          <span className="font-mono tabular-nums">
            <span>{r.affectedUsers}</span>
            <Delta value={r.usersDelta} />
          </span>
        ),
      },
      {
        title: t('rum.common.actions', '操作'),
        key: 'actions',
        width: 160,
        fixed: 'right',
        render: (_: unknown, r: RumReleaseRow) => (
          <div
            className="flex flex-wrap items-center gap-2"
            onClick={(e) => e.stopPropagation()}
          >
            <RumIconAction
              title={t('rum.releases.viewErrors', '查看错误')}
              onClick={() => router.push(errorsHref(r.release))}
            />
            {r.isBaseline ? (
              <span className="text-xs text-[var(--color-text-3)]">
                {t('rum.releases.currentBaseline', '当前基线')}
              </span>
            ) : application ? (
              <RumPermission resource="releases" action="Operate">
                <Popconfirm
                  title={t('rum.releases.baselineConfirm', '将「{v}」设为基线？', {
                    v: r.release,
                  })}
                  onConfirm={() => void setBaseline(r)}
                  okText={t('rum.releases.setBaseline', '设为基线')}
                  cancelText={t('rum.common.cancel', '取消')}
                >
                  <span className="inline-flex">
                    <RumIconAction
                      title={t('rum.releases.setBaseline', '设为基线')}
                      loading={settingBaseline === r.release}
                    />
                  </span>
                </Popconfirm>
              </RumPermission>
            ) : (
              <Tooltip title={t('rum.releases.selectAppForBaseline', '请先选择应用后再设基线')}>
                <span className="inline-flex">
                  <RumIconAction title={t('rum.releases.setBaseline', '设为基线')} disabled />
                </span>
              </Tooltip>
            )}
          </div>
        ),
      },
    ],
    [t, application, settingBaseline, range, router],
  );

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t('rum.releases.title', '部署追踪')}</h1>
      {degrade ? <div className="mb-2 shrink-0"><PipelineDegradedBanner reason={degrade} /></div> : null}

      <RumSingleWorkbench
        toolbar={
          <RumListToolbar
            spacing="flush"
            leading={
              <Segmented
                value={tab}
                onChange={(val) => setTab(String(val))}
                options={[
                  { value: 'releases', label: t('rum.releases.title', '部署追踪') },
                  { value: 'sourcemaps', label: t('rum.sourcemaps.title', 'SourceMap 管理') },
                ]}
              />
            }
            trailing={
              <>
                {tab === 'releases' ? (
                  <RumRangeSegmented value={range} loading={pending} onChange={setRange} />
                ) : null}
                <Select
                  value={application || undefined}
                  allowClear
                  placeholder={t('rum.filter.allApps', '全部应用')}
                  options={apps.map((name) => ({ value: name, label: name }))}
                  onChange={(value) => setApplication(value || '')}
                  className="min-w-40 w-44"
                />
                {tab === 'releases' ? (
                  <>
                    <TrafficScopeControl />
                    <ExportButton
                      rows={rows as unknown as Record<string, unknown>[]}
                      filename="rum-releases"
                      truncated={rows.length > 500}
                    />
                  </>
                ) : application ? (
                  <RumPermission resource="releases" action="Operate">
                    <Button
                      icon={<KeyOutlined aria-hidden="true" />}
                      loading={rotatingToken}
                      onClick={() => void rotateCiToken()}
                    >
                      {t('rum.sourcemaps.rotateToken', '轮换 CI Token')}
                    </Button>
                  </RumPermission>
                ) : (
                  <Tooltip
                    title={t(
                      'rum.sourcemaps.selectApplication',
                      '先选择一个应用，再管理它的 SourceMap。',
                    )}
                  >
                    <span className="inline-flex">
                      <Button icon={<KeyOutlined aria-hidden="true" />} disabled>
                        {t('rum.sourcemaps.rotateToken', '轮换 CI Token')}
                      </Button>
                    </span>
                  </Tooltip>
                )}
              </>
            }
          />
        }
      >
        {tab === 'releases' ? (
          pending ? (
            <>
              <RumKpiSkeleton count={4} />
              <RumTableSkeleton size="middle" columns={rumSkeletonColumns(columns)} />
            </>
          ) : rows.length === 0 ? (
            <div className="flex min-h-0 flex-1 items-center justify-center">
              <Empty
                description={
                  <div className="flex flex-col gap-1">
                    <span>{t('rum.releases.empty', '没有版本样本')}</span>
                    <span className="text-xs text-[var(--color-text-3)]">
                      {t('rum.releases.emptyHint', '选择应用与时间范围后再试。')}
                    </span>
                  </div>
                }
              />
            </div>
          ) : rows.length > 0 ? (
            <>
              <RumMetricGrid
                cells={[
                  {
                    label: t('rum.releases.kpiVersions', '版本数'),
                    value: String(summary.versions),
                  },
                  {
                    label: t('rum.errors.title', '错误追踪'),
                    value: String(summary.errorCount),
                    tone: summary.errorCount > 0 ? 'danger' : 'success',
                  },
                  {
                    label: t('rum.releases.newIssues', '新增问题'),
                    value: String(summary.newIssues),
                    tone: summary.newIssues > 0 ? 'danger' : undefined,
                  },
                  {
                    label: t('rum.errors.detail.affectedSessions', '影响会话'),
                    value: String(summary.sessions),
                  },
                ]}
              />
              {!application ? (
                <p className="m-0 text-xs text-[var(--color-text-3)]">
                  {t(
                    'rum.releases.selectAppHint',
                    '当前为全部应用汇总。选择单个应用后可标记体验基线，并对比版本变化。',
                  )}
                </p>
              ) : null}
              <div className="min-h-0 min-w-0 flex-1">
                <CustomTable<RumReleaseRow>
                  rowKey="release"
                  size="middle"
                  dataSource={table.rows}
                  columns={columns}
                  pagination={{
                    current: table.pagination.current,
                    pageSize: table.pagination.pageSize,
                    total: table.pagination.total,
                    showSizeChanger: table.pagination.showSizeChanger,
                    onChange: table.pagination.onChange,
                  }}
                  tableLayout="fixed"
                  autoScrollX={false}
                  onRow={(record) => ({
                    className: 'cursor-pointer transition-colors hover:bg-[var(--color-fill-2)]',
                    onClick: () => router.push(errorsHref(record.release)),
                  })}
                />
              </div>
            </>
          ) : null
        ) : (
          <SourceMapManager
            application={application}
            releases={rows.map((row) => row.release)}
            initialRelease={searchParams.get('release') || ''}
            ciToken={ciToken}
          />
        )}
      </RumSingleWorkbench>
    </div>
  );
}
