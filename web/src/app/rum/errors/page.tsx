'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Empty, Select, type TableColumnsType } from 'antd';

import {
  useRumQueries,
  type RumErrorIssueItem,
  type RumErrorIssuePage,
} from '@/app/rum/api';
import RumIconAction from '@/app/rum/components/rum-icon-action';
import RumPermission from '@/app/rum/components/rum-permission';
import RumRangeSegmented from '@/app/rum/components/rum-range-segmented';
import {
  RumDualWorkbench,
  RumFilterBlock,
} from '@/app/rum/components/rum-dual-workbench';
import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import ExportButton from '@/app/rum/components/export-button';
import { RumTableSkeleton, rumSkeletonColumns } from '@/app/rum/components/rum-skeleton';
import TrafficScopeControl from '@/app/rum/components/traffic-scope';
import Sparkline from '@/app/apm/components/home/sparkline';
import { toneSemanticPalette, type CwvTone } from '@/app/rum/lib/cwv';
import SemanticBadge from '@/components/semantic-badge';
import { degradationReason } from '@/app/rum/lib/degradation';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { isProtectedRumMessage } from '@/app/rum/sessions/lib/timeline-error';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import { useRumClientPager } from '@/app/rum/lib/table-pagination';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';

const STATUS_FILTERS = ['all', 'active', 'open', 'reviewed', 'resolved', 'ignored'] as const;

const statusTone: Record<string, CwvTone> = {
  resolved: 'success',
  ignored: 'neutral',
  open: 'warning',
  reviewed: 'neutral',
};

function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function RumErrorsPage() {
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
  const { listErrors, listApplications, updateErrorIssue, authReady } = useRumQueries();

  const status = searchParams.get('status') || 'all';
  const sort = searchParams.get('orderBy') || 'count';
  const [page, setPage] = useState<RumErrorIssuePage | null>(null);
  const [apps, setApps] = useState<string[]>([]);
  const [pending, setPending] = useState(true);
  const [acting, setActing] = useState<string | null>(null);

  const query = useMemo(() => {
    const out: Record<string, string> = { range, orderBy: sort, traffic };
    if (application) out.application = application;
    if (status !== 'all') out.status = status;
    return out;
  }, [range, sort, traffic, application, status]);

  const load = useCallback(async () => {
    setPending(true);
    try {
      setPage(await listErrors(query));
    } catch {
      setPage(null);
    } finally {
      setPending(false);
    }
  }, [listErrors, query]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      setPending(true);
      void listErrors(query)
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
    [listErrors, query],
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

  const issues = page?.issues || [];
  const table = useRumClientPager(issues, `${range}|${application}|${status}|${sort}|${traffic}`);
  const degrade = degradationReason(page);

  async function triage(issue: RumErrorIssueItem, nextStatus: string) {
    setActing(issue.fingerprint);
    try {
      await updateErrorIssue(issue.fingerprint, { status: nextStatus });
      await load();
    } catch {
      // request toast is handled by useApiClient
    } finally {
      setActing(null);
    }
  }

  function actionsFor(statusLabel: string) {
    switch (statusLabel) {
      case 'open':
        return [
          ['reviewed', t('rum.errors.triage.markReviewed', '已审阅')],
          ['resolved', t('rum.errors.triage.resolve', '解决')],
          ['ignored', t('rum.errors.triage.ignore', '忽略')],
        ] as const;
      case 'reviewed':
        return [
          ['resolved', t('rum.errors.triage.resolve', '解决')],
          ['ignored', t('rum.errors.triage.ignore', '忽略')],
          ['open', t('rum.errors.triage.reopen', '重开')],
        ] as const;
      case 'resolved':
        return [['open', t('rum.errors.triage.reopen', '重开')]] as const;
      case 'ignored':
        return [
          ['open', t('rum.errors.triage.reopen', '重开')],
          ['resolved', t('rum.errors.triage.resolve', '解决')],
        ] as const;
      default:
        return [];
    }
  }

  const columns: TableColumnsType<RumErrorIssueItem> = [
    {
      title: t('rum.errors.message', '错误'),
      key: 'message',
      ellipsis: true,
      render: (_, issue) => {
        const raw = issue.sampleMessage || issue.normalizedMessage || '';
        const protectedMessage = isProtectedRumMessage(raw);
        // Free-text bodies are hashed at ingest; lead with type so every row isn't the same placeholder.
        const title = protectedMessage
          ? issue.errorType || t('rum.errors.untitled', '异常错误')
          : raw || issue.errorType || '—';
        const subtitleParts = [
          protectedMessage ? t('rum.errors.privateMessage', '消息已隐私化') : null,
          !protectedMessage && issue.errorType && issue.errorType !== title ? issue.errorType : null,
          issue.lastRelease || null,
        ].filter(Boolean);
        const detailHref = `/rum/errors/detail?fingerprint=${encodeURIComponent(issue.fingerprint)}&application=${encodeURIComponent(issue.application)}&range=${range}`;
        return (
          <div className="flex min-w-0 flex-col gap-0.5 py-0.5">
            <div className="flex min-w-0 items-center gap-1.5">
              <Link
                href={detailHref}
                className="truncate transition-colors hover:text-[var(--color-primary)] hover:underline group-hover:text-[var(--color-primary)]"
                title={title}
                onClick={(e) => e.stopPropagation()}
              >
                {title}
              </Link>
              {issue.signals?.includes('new') ? (
                <SemanticBadge label={t('rum.errors.signal.new', '新增')} {...toneSemanticPalette('info')} />
              ) : null}
              {issue.signals?.includes('regression') ? (
                <SemanticBadge label={t('rum.errors.signal.regression', '疑似回归')} {...toneSemanticPalette('danger')} />
              ) : null}
            </div>
            {subtitleParts.length > 0 ? (
              <div className="truncate text-xs text-[var(--color-text-3)]">{subtitleParts.join(' · ')}</div>
            ) : null}
          </div>
        );
      },
    },
    {
      title: t('rum.applications.application', '应用'),
      key: 'application',
      width: 128,
      render: (_, issue) => (
        <span className="truncate">{issue.application}</span>
      ),
    },
    {
      title: t('rum.errors.sessions', '会话'),
      key: 'sessions',
      width: 72,
      render: (_, issue) => <span className="tabular-nums">{issue.affectedSessions}</span>,
    },
    {
      title: t('rum.errors.users', '用户数'),
      key: 'users',
      width: 72,
      render: (_, issue) => <span className="tabular-nums">{issue.affectedUsers}</span>,
    },
    {
      title: t('rum.errors.count', '次数'),
      key: 'count',
      width: 72,
      render: (_, issue) => <span className="tabular-nums">{issue.count}</span>,
    },
    {
      title: t('rum.common.trend', '趋势'),
      key: 'trend',
      width: 96,
      render: (_, issue) =>
        issue.sparkline?.length ? (
          <Sparkline data={issue.sparkline} width={56} height={14} color="var(--color-text-3)" fit="fixed" />
        ) : (
          <span className="text-[var(--color-text-4)]">—</span>
        ),
    },
    {
      title: t('rum.errors.lastSeen', '最近出现'),
      key: 'lastSeen',
      width: 128,
      render: (_, issue) => (
        <span className="tabular-nums">{formatWhen(issue.lastSeen)}</span>
      ),
    },
    {
      title: t('rum.errors.status', '状态'),
      key: 'status',
      width: 88,
      render: (_, issue) => {
        const statusLabel = issue.status || 'open';
        return (
          <SemanticBadge
            label={t(`rum.errors.statusLabel.${statusLabel}`, statusLabel)}
            {...toneSemanticPalette(statusTone[statusLabel] || 'neutral')}
          />
        );
      },
    },
    {
      title: t('rum.common.actions', '操作'),
      key: 'actions',
      width: 148,
      fixed: 'right',
      render: (_, issue) => {
        const actions = actionsFor(issue.status || 'open');
        return (
          <div className="flex items-center" onClick={(e) => e.stopPropagation()}>
            <RumPermission
              resource="errors"
              action="Operate"
              className="inline-flex items-center gap-2"
            >
              {actions.map(([next, label]) => (
                <RumIconAction
                  key={next}
                  title={label}
                  disabled={acting === issue.fingerprint}
                  onClick={() => void triage(issue, next)}
                />
              ))}
            </RumPermission>
          </div>
        );
      },
    },
  ];

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t('rum.errors.title', '错误追踪')}</h1>

      {degrade ? <div className="mb-2 shrink-0"><PipelineDegradedBanner reason={degrade} /></div> : null}

      <RumDualWorkbench
        asideTitle={t('rum.errors.filterTitle', '错误筛选')}
        aside={
          <>
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
            <RumFilterBlock title={t('rum.errors.status', '状态')}>
              <Select
                size="small"
                className="w-full"
                value={status}
                onChange={(value) => setParams({ status: value === 'all' ? null : value })}
                options={STATUS_FILTERS.map((key) => ({
                  value: key,
                  label: t(`rum.errors.filter.${key}`, key),
                }))}
              />
            </RumFilterBlock>
            <RumFilterBlock title={t('rum.traffic.label', '流量')}>
              <TrafficScopeControl block size="small" />
            </RumFilterBlock>
          </>
        }
        mainTitle={t('rum.errors.title', '错误追踪')}
        mainExtra={
          issues.length > 0 ? (
            <span className="tabular-nums text-[var(--color-text-3)]">
              {t('rum.errors.rowCount', '{n} 条', { n: issues.length })}
            </span>
          ) : null
        }
        main={
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
            <div className="flex h-8 shrink-0 flex-wrap items-center justify-end gap-2">
              <Select
                value={sort}
                className="h-8 w-[120px] [&_.ant-select-selector]:!h-8 [&_.ant-select-selector]:!items-center"
                onChange={(value) => setParams({ orderBy: value })}
                options={[
                  { value: 'count', label: t('rum.errors.sort.count', '次数') },
                  { value: 'sessions', label: t('rum.errors.sort.sessions', '会话') },
                  { value: 'users', label: t('rum.errors.sort.users', '用户') },
                  { value: 'relevance', label: t('rum.errors.sort.relevance', '相关度') },
                ]}
              />
              <ExportButton
                rows={issues as unknown as Record<string, unknown>[]}
                filename="rum-errors"
              />
            </div>

            {pending ? (
              <RumTableSkeleton columns={rumSkeletonColumns(columns)} />
            ) : issues.length === 0 ? (
              <div className="flex min-h-0 flex-1 items-center justify-center">
                <Empty description={t('rum.errors.empty', '没有错误样本')} />
              </div>
            ) : (
              <div className="min-h-0 min-w-0 flex-1">
                <CustomTable<RumErrorIssueItem>
                  rowKey="fingerprint"
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
                  onRow={(issue) => ({
                    onClick: () =>
                      router.push(
                        `/rum/errors/detail?fingerprint=${encodeURIComponent(issue.fingerprint)}&application=${encodeURIComponent(issue.application)}&range=${range}`,
                      ),
                    className: 'group cursor-pointer transition-colors hover:bg-[var(--color-fill-2)]',
                  })}
                />
              </div>
            )}
          </div>
        }
      />
    </div>
  );
}
