'use client';

import { useCallback, useMemo, useRef, useState, type MouseEvent } from 'react';
import Link from 'next/link';
import { BellOutlined, ExportOutlined } from '@ant-design/icons';
import { Drawer, Empty, Segmented, Timeline, type TableColumnsType } from 'antd';

import {
  useRumQueries,
  type RumAlertEventDetail,
  type RumAlertEventItem,
  type RumMonitorItem,
} from '@/app/rum/api';
import CustomTable from '@/components/custom-table';
import Sparkline from '@/app/apm/components/home/sparkline';
import RumIconAction from '@/app/rum/components/rum-icon-action';
import RumListToolbar from '@/app/rum/components/rum-list-toolbar';
import { RumSingleWorkbench } from '@/app/rum/components/rum-dual-workbench';
import { RumMetricGrid } from '@/app/rum/components/rum-metric-card';
import RumRefreshButton from '@/app/rum/components/rum-refresh-button';
import { RumAlertDetailSkeleton, RumTableSkeleton, rumSkeletonColumns } from '@/app/rum/components/rum-skeleton';
import SemanticBadge from '@/components/semantic-badge';
import { toneSemanticPalette } from '@/app/rum/lib/cwv';
import { useRumClientPager } from '@/app/rum/lib/table-pagination';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import { useTranslation } from '@/utils/i18n';

const ALERT_EVENT_LIMIT = 200;

const statusTone: Record<string, 'danger' | 'warning' | 'success' | 'neutral'> = {
  firing: 'danger',
  pending: 'warning',
  resolved: 'success',
};

const severityTone: Record<string, 'info' | 'warning' | 'danger' | 'neutral'> = {
  info: 'info',
  warning: 'warning',
  critical: 'danger',
};

function formatWhen(iso?: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatValue(metric: string, value: number): string {
  if (metric === 'error_rate') return `${(value * 100).toFixed(2)}%`;
  if (metric === 'cls_p75') return value.toFixed(3);
  return `${Math.round(value)}ms`;
}

function eventExplanation(
  t: (key: string, fallback?: string) => string,
  policy: RumMonitorItem | undefined,
  event: RumAlertEventItem,
): string {
  const metric = policy?.metric
    ? t(`rum.monitors.metric.${policy.metric}`, policy.metric)
    : t('rum.alertEvents.value', '指标值');
  const threshold = event.message.toLowerCase().includes('critical')
    ? t('rum.alertEvents.breachedCritical', '突破严重阈值')
    : t('rum.alertEvents.breachedWarn', '突破警告阈值');
  return `${metric} · ${threshold}`;
}

export default function RumAlertEventsPage() {
  const { t } = useTranslation();
  const { listAlertEvents, getAlertEvent, listMonitors, authReady } = useRumQueries();
  const [tab, setTab] = useState<'active' | 'history'>('active');
  const [items, setItems] = useState<RumAlertEventItem[]>([]);
  const [policies, setPolicies] = useState<RumMonitorItem[]>([]);
  const [pending, setPending] = useState(true);
  const [detail, setDetail] = useState<RumAlertEventDetail | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const load = useCallback(async () => {
    setPending(true);
    try {
      const [events, monitors] = await Promise.all([
        listAlertEvents(1, ALERT_EVENT_LIMIT),
        listMonitors(),
      ]);
      setItems(events.items);
      setPolicies(monitors);
    } catch {
      setItems([]);
    } finally {
      setPending(false);
    }
  }, [listAlertEvents, listMonitors]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      setPending(true);
      void Promise.all([listAlertEvents(1, ALERT_EVENT_LIMIT), listMonitors()])
        .then(([events, monitors]) => {
          if (isCancelled()) return;
          setItems(events.items);
          setPolicies(monitors);
        })
        .catch(() => {
          if (!isCancelled()) setItems([]);
        })
        .finally(() => {
          if (!isCancelled()) setPending(false);
        });
    },
    [listAlertEvents, listMonitors],
  );

  const policyById = useMemo(() => new Map(policies.map((p) => [p.id, p])), [policies]);

  const filtered = useMemo(() => {
    if (tab === 'active') return items.filter((ev) => ev.status !== 'resolved');
    return items.filter((ev) => ev.status === 'resolved');
  }, [items, tab]);
  const table = useRumClientPager(filtered, tab);

  const activeCount = items.filter((ev) => ev.status !== 'resolved').length;

  const openDetail = useCallback(
    async (ev: RumAlertEventItem) => {
      try {
        setDetail(await getAlertEvent(ev.id));
        setDrawerOpen(true);
      } catch {
        // request toast is handled by useApiClient
      }
    },
    [getAlertEvent],
  );

  const columns = useMemo<TableColumnsType<RumAlertEventItem>>(
    () => [
      {
        title: t('rum.alertEvents.policy', '策略'),
        key: 'policy',
        width: 200,
        ellipsis: true,
        render: (_: unknown, ev: RumAlertEventItem) => {
          const name = policyById.get(ev.policyId)?.name || ev.policyId.slice(0, 8);
          return (
            <span className="truncate" title={name}>
              {name}
            </span>
          );
        },
      },
      {
        title: t('rum.alertEvents.status', '状态'),
        key: 'status',
        width: 88,
        render: (_: unknown, ev: RumAlertEventItem) => (
          <SemanticBadge
            label={t(`rum.alertEvents.statusLabel.${ev.status}`, ev.status)}
            {...toneSemanticPalette(statusTone[ev.status] ?? 'neutral')}
          />
        ),
      },
      {
        title: t('rum.alertEvents.severity', '严重级别'),
        key: 'severity',
        width: 96,
        render: (_: unknown, ev: RumAlertEventItem) => {
          const severity = policyById.get(ev.policyId)?.severity || 'warning';
          return (
            <SemanticBadge
              label={t(`rum.monitors.severity.${severity}`, severity)}
              {...toneSemanticPalette(severityTone[severity] ?? 'neutral')}
            />
          );
        },
      },
      {
        title: t('rum.alertEvents.value', '指标值'),
        key: 'value',
        width: 104,
        render: (_: unknown, ev: RumAlertEventItem) => (
          <span className="font-mono tabular-nums">
            {formatValue(policyById.get(ev.policyId)?.metric ?? '', ev.metricValue)}
          </span>
        ),
      },
      {
        title: t('rum.alertEvents.message', '说明'),
        key: 'message',
        ellipsis: true,
        render: (_: unknown, ev: RumAlertEventItem) => (
          <span className="truncate">
            {eventExplanation(t, policyById.get(ev.policyId), ev)}
          </span>
        ),
      },
      {
        title: t('rum.alertEvents.firedAt', '触发时间'),
        key: 'firedAt',
        width: 140,
        render: (_: unknown, ev: RumAlertEventItem) => (
          <span className="tabular-nums">
            {formatWhen(ev.firedAt || ev.createdAt)}
          </span>
        ),
      },
      {
        title: t('rum.common.actions', '操作'),
        key: 'actions',
        width: 72,
        fixed: 'right',
        render: (_: unknown, ev: RumAlertEventItem) => (
          <div onClick={(e) => e.stopPropagation()}>
            <RumIconAction
              title={t('rum.alertEvents.viewDetail', '详情')}
              onClick={() => void openDetail(ev)}
            />
          </div>
        ),
      },
    ],
    [t, policyById, openDetail],
  );

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t('rum.alertEvents.title', '告警')}</h1>
      <RumSingleWorkbench
        toolbar={
          <RumListToolbar
            spacing="flush"
            leading={
              <div className="flex min-w-0 flex-wrap items-center gap-3">
                <Segmented
                  value={tab}
                  onChange={(key) => setTab(key as 'active' | 'history')}
                  options={[
                    {
                      value: 'active',
                      label: (
                        <span className="inline-flex items-center gap-1.5">
                          <span>{t('rum.alertEvents.tabActive', '进行中')}</span>
                          {activeCount > 0 ? (
                            <span className="rounded-full bg-[var(--color-fail)] px-1.5 py-0.5 text-[10px] font-medium leading-none text-white tabular-nums">
                              {activeCount}
                            </span>
                          ) : null}
                        </span>
                      ),
                    },
                    { value: 'history', label: t('rum.alertEvents.tabHistory', '历史') },
                  ]}
                />
                <Link
                  href="/alarm/alarms"
                  className="inline-flex shrink-0 items-center gap-1 text-xs text-[var(--color-text-3)] hover:text-[var(--color-text-1)]"
                >
                  <ExportOutlined aria-hidden="true" className="text-[11px]" />
                  {t('rum.alertEvents.openInCenter', '告警中心')}
                </Link>
              </div>
            }
            trailing={<RumRefreshButton onClick={() => void load()} />}
          />
        }
      >
        {pending && items.length === 0 ? (
          <RumTableSkeleton size="middle" columns={rumSkeletonColumns(columns)} />
        ) : !pending && filtered.length === 0 ? (
          <div className="flex min-h-0 flex-1 items-center justify-center">
            <Empty
              description={
                <div className="flex flex-col gap-1">
                  <span>{t('rum.alertEvents.empty', '暂无告警')}</span>
                  <span className="text-xs text-[var(--color-text-3)]">
                    {t('rum.alertEvents.emptyHint', '策略触发后会出现在这里。')}
                  </span>
                </div>
              }
            />
          </div>
        ) : filtered.length > 0 ? (
          <div className="min-h-0 min-w-0 flex-1">
            <CustomTable<RumAlertEventItem>
              rowKey="id"
              size="middle"
              tableLayout="fixed"
              autoScrollX={false}
              dataSource={table.rows}
              columns={columns}
              pagination={{
                current: table.pagination.current,
                pageSize: table.pagination.pageSize,
                total: table.pagination.total,
                showSizeChanger: table.pagination.showSizeChanger,
                onChange: table.pagination.onChange,
              }}
              onRow={(ev) => ({
                className: 'cursor-pointer transition-colors hover:bg-[var(--color-fill-2)]',
                onClick: () => void openDetail(ev),
              })}
            />
          </div>
        ) : null}
      </RumSingleWorkbench>

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        width={560}
        title={detail ? detail.policy.name || t('rum.alertEvents.title', '告警') : t('rum.alertEvents.title', '告警')}
      >
        {detail ? (
          <AlertEventDetailView detail={detail} t={t} />
        ) : (
          <RumAlertDetailSkeleton />
        )}
      </Drawer>
    </div>
  );
}

function AlertEventDetailView({
  detail,
  t,
}: {
  detail: RumAlertEventDetail;
  t: (key: string, fallback?: string) => string;
}) {
  const ev = detail.event;
  const eventSeverity = detail.policy.severity || 'warning';

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border-2)] pb-3">
        <SemanticBadge
          label={t(`rum.alertEvents.statusLabel.${ev.status}`, ev.status)}
          {...toneSemanticPalette(statusTone[ev.status] ?? 'neutral')}
        />
        <SemanticBadge
          label={t(`rum.monitors.severity.${eventSeverity}`, eventSeverity)}
          {...toneSemanticPalette(severityTone[eventSeverity] ?? 'neutral')}
        />
        <span className="ml-auto font-mono text-xs text-[var(--color-text-3)]">
          {detail.policy.application}
        </span>
      </div>

      <RumMetricGrid
        className="!grid-cols-2"
        cells={[
          {
            label: t('rum.alertEvents.value', '指标值'),
            value: formatValue(detail.policy.metric ?? '', ev.metricValue),
          },
          {
            label: t('rum.alertEvents.firedAt', '触发时间'),
            value: formatWhen(ev.firedAt || ev.createdAt),
          },
          {
            label: t('rum.alertEvents.resolvedAt', '恢复时间'),
            value: formatWhen(ev.resolvedAt),
          },
          {
            label: t('rum.alertEvents.message', '说明'),
            value: eventExplanation(t, detail.policy, ev),
          },
        ]}
      />

      <div className="space-y-2">
        <div className="border-b border-[var(--color-border-2)] pb-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-3)]">
          {t('rum.alertEvents.trend', '指标趋势')}
        </div>
        <AlertMetricTrend
          points={detail.trend}
          emptyLabel={t('rum.alertEvents.trendEmpty', '该时间窗内暂无样本')}
          hoverHint={t('rum.alertEvents.trendHover', '移入查看数值')}
          formatPoint={(atMs, value) =>
            `${formatWhen(new Date(atMs).toISOString())} · ${formatValue(detail.policy.metric ?? '', value)}`
          }
        />
      </div>

      <div className="space-y-2">
        <div className="border-b border-[var(--color-border-2)] pb-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-3)]">
          {t('rum.alertEvents.detailTimeline', '时间线')}
        </div>
        {detail.timeline.length === 0 ? (
          <p className="text-xs text-[var(--color-text-3)]">{t('rum.alertEvents.emptyHint', '策略触发后会出现在这里。')}</p>
        ) : (
          <div className="pt-2">
            <Timeline
              items={detail.timeline.map((node, i) => ({
                key: `${node.kind}-${i}`,
                color: node.kind === 'fired' ? '#ef4444' : node.kind === 'resolved' ? '#10b981' : '#97a1ae',
                children: (
                  <div>
                    <div className="flex items-baseline gap-2">
                      <span className="inline-flex items-center gap-1 text-xs font-medium">
                        <BellOutlined className="text-[var(--color-text-3)]" />
                        {t(
                          `rum.alertEvents.timeline${node.kind[0].toUpperCase()}${node.kind.slice(1)}`,
                          node.kind,
                        )}
                      </span>
                      <span className="text-[11px] tabular-nums text-[var(--color-text-3)]">
                        {formatWhen(node.at)}
                      </span>
                    </div>
                    {node.note ? (
                      <p className="mt-0.5 text-xs text-[var(--color-text-3)]">{node.note}</p>
                    ) : null}
                  </div>
                ),
              }))}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function AlertMetricTrend({
  points,
  emptyLabel,
  hoverHint,
  formatPoint,
}: {
  points: { atMs: number; value: number }[];
  emptyLabel: string;
  hoverHint: string;
  formatPoint: (atMs: number, value: number) => string;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const values = useMemo(() => points.map((p) => Number(p.value) || 0), [points]);
  const hasSignal = values.some((v) => v > 0);

  const onMove = useCallback(
    (event: MouseEvent<HTMLDivElement>) => {
      const el = trackRef.current;
      if (!el || points.length === 0) return;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0) return;
      const ratio = (event.clientX - rect.left) / rect.width;
      const idx = Math.round(ratio * (points.length - 1));
      setHoverIdx(Math.max(0, Math.min(points.length - 1, idx)));
    },
    [points.length],
  );

  if (points.length === 0 || !hasSignal) {
    return <p className="text-xs text-[var(--color-text-3)]">{emptyLabel}</p>;
  }

  const active = hoverIdx != null ? points[hoverIdx] : null;
  const tipLeft =
    hoverIdx == null || points.length <= 1 ? 50 : (hoverIdx / (points.length - 1)) * 100;

  return (
    <div
      ref={trackRef}
      className="relative h-24 cursor-crosshair pt-2"
      onMouseMove={onMove}
      onMouseLeave={() => setHoverIdx(null)}
    >
      <Sparkline data={values} height={88} kind="area" color="var(--color-primary)" />
      {active ? (
        <>
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-2 w-px bg-[var(--color-primary)] opacity-40"
            style={{ left: `${tipLeft}%` }}
          />
          <div
            className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 whitespace-nowrap rounded-md bg-[var(--color-bg)] px-2 py-1 text-[11px] font-mono tabular-nums text-[var(--color-text-1)] shadow-sm ring-1 ring-[var(--color-border-2)]"
            style={{ left: `${tipLeft}%` }}
          >
            {formatPoint(Number(active.atMs) || 0, Number(active.value) || 0)}
          </div>
        </>
      ) : (
        <p className="pointer-events-none absolute left-0 top-0 text-[11px] text-[var(--color-text-4)]">
          {hoverHint}
        </p>
      )}
    </div>
  );
}
