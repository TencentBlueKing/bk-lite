'use client';

import { useCallback, useMemo, useRef, useState, type MouseEvent } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { BellOutlined, ExportOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Checkbox, Drawer, Empty, Input, Select, Tabs, Timeline, type TableColumnsType } from 'antd';

import {
  useRumQueries,
  type RumAlertDeliveryItem,
  type RumAlertEventDetail,
  type RumAlertItem,
  type RumAlertTimelineEvent,
} from '@/app/rum/api';
import AlertHandlerActions from '@/app/rum/alert-events/alert-handler-actions';
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
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import { useTranslation } from '@/utils/i18n';

const statusTone: Record<string, 'danger' | 'warning' | 'success' | 'neutral'> = {
  active: 'danger',
  recovered: 'success',
  closed: 'neutral',
};

const severityTone: Record<string, 'info' | 'warning' | 'danger' | 'neutral'> = {
  info: 'info',
  warning: 'warning',
  critical: 'danger',
};

function formatWhen(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatValue(metric: string, value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  if (metric === 'error_rate') return `${(value * 100).toFixed(2)}%`;
  if (metric === 'cls_p75') return value.toFixed(3);
  if (metric === 'session_count') return String(Math.round(value));
  return `${Math.round(value)}ms`;
}

export default function RumAlertEventsPage() {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const eventId = searchParams.get('event')?.trim() || '';
  const { listAlertEvents, getAlertEvent, listApplications, retryAlertDelivery, authReady } = useRumQueries();
  const [tab, setTab] = useState<'active' | 'history'>('active');
  const [myAlert, setMyAlert] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [application, setApplication] = useState('');
  const [apps, setApps] = useState<string[]>([]);
  const [items, setItems] = useState<RumAlertItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);
  const [pending, setPending] = useState(true);
  const [detail, setDetail] = useState<RumAlertEventDetail | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const load = useCallback(async () => {
    setPending(true);
    try {
      const events = await listAlertEvents({
        status: tab,
        application,
        keyword: keyword.trim(),
        myAlert,
        page,
        limit: pageSize,
      });
      setItems(events.items);
      setTotal(events.total);
    } catch {
      setItems([]);
      setTotal(0);
    } finally {
      setPending(false);
    }
  }, [application, keyword, listAlertEvents, myAlert, page, pageSize, tab]);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      setPending(true);
      void listAlertEvents({
        status: tab,
        application,
        keyword: keyword.trim(),
        myAlert,
        page,
        limit: pageSize,
      })
        .then((events) => {
          if (isCancelled()) return;
          setItems(events.items);
          setTotal(events.total);
        })
        .catch(() => {
          if (!isCancelled()) {
            setItems([]);
            setTotal(0);
          }
        })
        .finally(() => {
          if (!isCancelled()) setPending(false);
        });
    },
    [application, keyword, listAlertEvents, myAlert, page, pageSize, tab],
  );

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      void listApplications()
        .then((list) => {
          if (!isCancelled()) setApps(list.map((item) => item.application).filter(Boolean));
        })
        .catch(() => {
          if (!isCancelled()) setApps([]);
        });
    },
    [listApplications],
  );

  const openDetail = useCallback(
    async (id: string) => {
      try {
        setDetail(await getAlertEvent(id));
        setDrawerOpen(true);
      } catch {
        // request toast is handled by useApiClient
      }
    },
    [getAlertEvent],
  );

  useRumAuthedEffect(
    authReady && Boolean(eventId),
    (isCancelled) => {
      void getAlertEvent(eventId)
        .then((next) => {
          if (isCancelled()) return;
          setDetail(next);
          setDrawerOpen(true);
        })
        .catch(() => undefined);
    },
    [eventId, getAlertEvent],
  );

  const columns = useMemo<TableColumnsType<RumAlertItem>>(
    () => [
      {
        title: t('rum.alertEvents.name', '名称'),
        key: 'name',
        ellipsis: true,
        render: (_: unknown, ev: RumAlertItem) => (
          <span className="truncate" title={ev.policyName || ev.policyId}>
            {ev.policyName || ev.policyId}
          </span>
        ),
      },
      {
        title: t('rum.alertEvents.severity', '级别'),
        key: 'severity',
        width: 96,
        render: (_: unknown, ev: RumAlertItem) => (
          <SemanticBadge
            label={t(`rum.monitors.severity.${ev.severity || 'warning'}`, ev.severity || 'warning')}
            {...toneSemanticPalette(severityTone[ev.severity || ''] ?? 'neutral')}
          />
        ),
      },
      {
        title: t('rum.alertEvents.status', '状态'),
        key: 'status',
        width: 96,
        render: (_: unknown, ev: RumAlertItem) => (
          <SemanticBadge
            label={t(`rum.alertEvents.statusLabel.${ev.status}`, ev.status)}
            {...toneSemanticPalette(statusTone[ev.status] ?? 'neutral')}
          />
        ),
      },
      {
        title: t('rum.alertEvents.metricValue', '指标 / 值'),
        key: 'metric',
        width: 160,
        render: (_: unknown, ev: RumAlertItem) => (
          <span className="tabular-nums">
            {t(`rum.monitors.metric.${ev.metric || ''}`, ev.metric || '—')} · {formatValue(ev.metric || '', ev.currentValue)}
          </span>
        ),
      },
      {
        title: t('rum.alertEvents.handlers', '处理人'),
        key: 'handlers',
        width: 140,
        ellipsis: true,
        render: (_: unknown, ev: RumAlertItem) => (
          <span className="truncate">{(ev.handlersDisplay || ev.handlers || []).map(String).join(', ') || '—'}</span>
        ),
      },
      {
        title: t('rum.alertEvents.notification', '通知'),
        key: 'notification',
        width: 140,
        render: (_: unknown, ev: RumAlertItem) => {
          const note = ev.notification;
          if (!note) return '—';
          return (
            <span className="tabular-nums">
              {t('rum.alertEvents.deliveryStatus.delivered', '已投递')} {note.delivered} · {t('rum.alertEvents.deliveryStatus.failed', '失败')} {note.failed}
            </span>
          );
        },
      },
      {
        title: t('rum.applications.application', '应用'),
        key: 'application',
        width: 140,
        ellipsis: true,
        render: (_: unknown, ev: RumAlertItem) => <span className="truncate">{ev.application || '—'}</span>,
      },
      {
        title: t('rum.alertEvents.firedAt', '触发时间'),
        key: 'startedAt',
        width: 140,
        render: (_: unknown, ev: RumAlertItem) => (
          <span className="tabular-nums">{formatWhen(ev.startedAt || ev.createdAt)}</span>
        ),
      },
      {
        title: t('rum.common.actions', '操作'),
        key: 'actions',
        width: 220,
        fixed: 'right',
        render: (_: unknown, ev: RumAlertItem) => (
          <div className="flex items-center gap-2" onClick={(event) => event.stopPropagation()}>
            <RumIconAction
              title={t('rum.alertEvents.viewDetail', '详情')}
              onClick={() => void openDetail(ev.id)}
            />
            <AlertHandlerActions alert={ev} onDone={() => void load()} />
          </div>
        ),
      },
    ],
    [load, openDetail, t],
  );

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t('rum.alertEvents.title', '告警')}</h1>
      <RumSingleWorkbench
        toolbar={
          <RumListToolbar
            spacing="flush"
            leading={
              <Tabs
                activeKey={tab}
                onChange={(key) => {
                  setTab(key as 'active' | 'history');
                  setPage(1);
                }}
                items={[
                  { key: 'active', label: t('rum.alertEvents.tabActive', '活跃告警') },
                  { key: 'history', label: t('rum.alertEvents.tabHistory', '历史告警') },
                ]}
              />
            }
            trailing={
              <>
                <Checkbox
                  checked={myAlert}
                  onChange={(event) => {
                    setMyAlert(event.target.checked);
                    setPage(1);
                  }}
                >
                  {t('rum.alertEvents.myAlert', '我的告警')}
                </Checkbox>
                <Select
                  allowClear
                  placeholder={t('rum.filter.allApps', '全部应用')}
                  value={application || undefined}
                  onChange={(value) => {
                    setApplication(value || '');
                    setPage(1);
                  }}
                  className="min-w-40 w-44"
                  options={apps.map((app) => ({ value: app, label: app }))}
                />
                <Input
                  allowClear
                  prefix={<SearchOutlined className="text-[var(--color-text-3)]" />}
                  placeholder={t('rum.alertEvents.searchPlaceholder', '搜索告警…')}
                  value={keyword}
                  onChange={(event) => {
                    setKeyword(event.target.value);
                    setPage(1);
                  }}
                  className="!h-8 w-60 !items-center !py-0"
                />
                <Link
                  href="/alarm/alarms"
                  className="inline-flex shrink-0 items-center gap-1 text-[var(--color-text-3)] hover:text-[var(--color-text-1)]"
                >
                  <ExportOutlined aria-hidden="true" />
                  {t('rum.alertEvents.openInCenter', '告警中心')}
                </Link>
                <RumRefreshButton onClick={() => void load()} />
              </>
            }
          />
        }
      >
        {pending && items.length === 0 ? (
          <RumTableSkeleton size="middle" columns={rumSkeletonColumns(columns)} />
        ) : (
          <div className="min-h-0 min-w-0 flex-1">
            <CustomTable<RumAlertItem>
              rowKey="id"
              size="middle"
              tableLayout="fixed"
              autoScrollX={false}
              dataSource={items}
              columns={columns}
              locale={{
                emptyText: (
                  <Empty
                    description={
                      <div className="flex flex-col gap-1">
                        <span>{t('rum.alertEvents.empty', '暂无告警')}</span>
                        <span className="text-[var(--color-text-3)]">
                          {t('rum.alertEvents.emptyHint', '策略触发后会出现在这里。')}
                        </span>
                      </div>
                    }
                  />
                ),
              }}
              pagination={{
                current: page,
                pageSize,
                total,
                showSizeChanger: true,
                onChange: (nextPage, nextSize) => {
                  setPage(nextPage);
                  setPageSize(nextSize);
                },
              }}
              onRow={(ev) => ({
                className: 'cursor-pointer transition-colors hover:bg-[var(--color-fill-2)]',
                onClick: () => void openDetail(ev.id),
              })}
            />
          </div>
        )}
      </RumSingleWorkbench>

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        width={560}
        title={detail?.alert.policyName || t('rum.alertEvents.title', '告警')}
      >
        {detail ? (
          <AlertEventDetailView
            detail={detail}
            t={t}
            onRetry={async (deliveryId) => {
              await retryAlertDelivery(detail.alert.id, deliveryId);
              setDetail(await getAlertEvent(detail.alert.id));
            }}
          />
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
  onRetry,
}: {
  detail: RumAlertEventDetail;
  t: (key: string, fallback?: string, values?: Record<string, unknown>) => string;
  onRetry: (deliveryId: string) => Promise<void>;
}) {
  const alert = detail.alert;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border-2)] pb-3">
        <SemanticBadge
          label={t(`rum.alertEvents.statusLabel.${alert.status}`, alert.status)}
          {...toneSemanticPalette(statusTone[alert.status] ?? 'neutral')}
        />
        <SemanticBadge
          label={t(`rum.monitors.severity.${alert.severity || 'warning'}`, alert.severity || 'warning')}
          {...toneSemanticPalette(severityTone[alert.severity || ''] ?? 'neutral')}
        />
        <span className="ml-auto">{alert.application}</span>
      </div>
      <RumMetricGrid
        className="!grid-cols-3"
        cells={[
          {
            label: t('rum.alertEvents.metricValue', '指标 / 值'),
            value: `${t(`rum.monitors.metric.${alert.metric || ''}`, alert.metric || '—')} · ${formatValue(alert.metric || '', alert.currentValue)}`,
          },
          { label: t('rum.alertEvents.firedAt', '触发时间'), value: formatWhen(alert.startedAt) },
          { label: t('rum.alertEvents.resolvedAt', '恢复时间'), value: formatWhen(alert.endedAt) },
          { label: t('rum.applications.application', '应用'), value: alert.application || '—' },
          {
            label: t('rum.alertEvents.handlers', '处理人'),
            value: (alert.handlersDisplay || alert.handlers || []).map(String).join(', ') || '—',
          },
          { label: t('rum.alertEvents.lastEventAt', '最后事件'), value: formatWhen(alert.lastEventAt) },
        ]}
      />
      <div className="space-y-2">
        <div className="border-b border-[var(--color-border-2)] pb-1.5 text-[var(--color-text-3)]">
          {t('rum.alertEvents.trend', '指标趋势')}
        </div>
        <AlertMetricTrend
          points={detail.trend}
          emptyLabel={t('rum.alertEvents.trendEmpty', '该时间窗内暂无样本')}
          hoverHint={t('rum.alertEvents.trendHover', '移入查看数值')}
          formatPoint={(atMs, value) => `${formatWhen(new Date(atMs).toISOString())} · ${formatValue(alert.metric || '', value)}`}
        />
      </div>
      <div className="space-y-2">
        <div className="border-b border-[var(--color-border-2)] pb-1.5 text-[var(--color-text-3)]">
          {t('rum.alertEvents.detailTimeline', '时间线')}
        </div>
        {detail.events.length === 0 ? (
          <p className="text-[var(--color-text-3)]">{t('rum.alertEvents.emptyHint', '策略触发后会出现在这里。')}</p>
        ) : (
          <Timeline
            items={detail.events.map((node) => ({
              key: node.id,
              children: <TimelineNode node={node} t={t} />,
            }))}
          />
        )}
      </div>
      <div className="space-y-2">
        <div className="border-b border-[var(--color-border-2)] pb-1.5 text-[var(--color-text-3)]">
          {t('rum.alertEvents.deliveries', '通知投递')}
        </div>
        {detail.deliveries.length === 0 ? (
          <p className="text-[var(--color-text-3)]">{t('rum.alertEvents.deliveriesEmpty', '还没有投递记录。')}</p>
        ) : (
          <ul className="space-y-2">
            {detail.deliveries.map((item) => (
              <DeliveryRow key={item.id} item={item} t={t} onRetry={onRetry} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function TimelineNode({
  node,
  t,
}: {
  node: RumAlertTimelineEvent;
  t: (key: string, fallback?: string) => string;
}) {
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="inline-flex items-center gap-1">
          <BellOutlined className="text-[var(--color-text-3)]" />
          {t(`rum.alertEvents.action.${node.action}`, node.action)}
        </span>
        <span className="tabular-nums text-[var(--color-text-3)]">{formatWhen(node.occurredAt)}</span>
      </div>
    </div>
  );
}

function DeliveryRow({
  item,
  t,
  onRetry,
}: {
  item: RumAlertDeliveryItem;
  t: (key: string, fallback?: string) => string;
  onRetry: (deliveryId: string) => Promise<void>;
}) {
  return (
    <li className="flex items-center justify-between gap-3">
      <span className="truncate">{item.channelName || '—'}</span>
      <span className="flex shrink-0 items-center gap-2 tabular-nums text-[var(--color-text-3)]">
        {t(`rum.alertEvents.deliveryStatus.${item.status}`, item.status)} · {item.attempts || 0}
        {item.lastErrorMessage ? ` · ${item.lastErrorMessage}` : ''}
        {item.status === 'failed' ? (
          <Button type="link" size="small" className="px-0" onClick={() => void onRetry(item.id).catch(() => undefined)}>
            {t('rum.alertEvents.retry', '重投')}
          </Button>
        ) : null}
      </span>
    </li>
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
  const values = useMemo(() => points.map((point) => Number(point.value) || 0), [points]);
  const hasSignal = values.some((value) => value > 0);

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
    return <p className="text-[var(--color-text-3)]">{emptyLabel}</p>;
  }

  const active = hoverIdx != null ? points[hoverIdx] : null;
  const tipLeft = hoverIdx == null || points.length <= 1 ? 50 : (hoverIdx / (points.length - 1)) * 100;
  return (
    <div ref={trackRef} className="relative h-24 cursor-crosshair pt-2" onMouseMove={onMove} onMouseLeave={() => setHoverIdx(null)}>
      <Sparkline data={values} height={88} kind="area" color="var(--color-primary)" />
      {active ? (
        <div
          className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 whitespace-nowrap rounded-md bg-[var(--color-bg)] px-2 py-1 tabular-nums text-[var(--color-text-1)] shadow-sm ring-1 ring-[var(--color-border-2)]"
          style={{ left: `${tipLeft}%` }}
        >
          {formatPoint(Number(active.atMs) || 0, Number(active.value) || 0)}
        </div>
      ) : (
        <p className="pointer-events-none absolute left-0 top-0 text-[var(--color-text-4)]">{hoverHint}</p>
      )}
    </div>
  );
}
