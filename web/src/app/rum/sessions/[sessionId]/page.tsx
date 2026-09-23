'use client';

import { useCallback, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import {
  ApiOutlined,
  CheckCircleOutlined,
  CheckOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  CompassOutlined,
  CopyOutlined,
  DashboardOutlined,
  EnvironmentOutlined,
  ExclamationCircleOutlined,
  InteractionOutlined,
  LaptopOutlined,
  MobileOutlined,
  PlayCircleFilled,
  PlayCircleOutlined,
  RightOutlined,
  TabletOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons';
import { Alert, Button, Empty, message, Segmented, Tag, Tooltip } from 'antd';

import { useRumQueries, type RumReplayManifest, type RumSessionJourney } from '@/app/rum/api';
import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import RumBackButton, { RumDetailTitle } from '@/app/rum/components/rum-back-button';
import { RumMetricGrid } from '@/app/rum/components/rum-metric-card';
import { RumSessionDetailSkeleton } from '@/app/rum/components/rum-skeleton';
import { cwvTone } from '@/app/rum/lib/cwv';
import { degradationReason } from '@/app/rum/lib/degradation';
import {
  displayRoute,
  formatDurationMs,
  parseBrowser,
  parseDevice,
  truncateMiddle,
} from '@/app/rum/lib/format';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import { presentTimelineError } from '@/app/rum/sessions/lib/timeline-error';
import { useTranslation } from '@/utils/i18n';

interface TimelineItem {
  id: string;
  at: number;
  kind: 'view' | 'action' | 'error' | 'vital' | 'network' | 'console';
  title: string;
  detail?: string;
  route?: string;
  raw?: Record<string, unknown>;
}

function buildTimeline(data: RumSessionJourney): TimelineItem[] {
  const items: TimelineItem[] = [];

  for (const v of data.views || []) {
    const route = String(v.route || v.viewName || '');
    items.push({
      id: String(v.eventId || `view-${items.length}`),
      at: Date.parse(String(v.timestamp || '')),
      kind: 'view',
      title: route ? displayRoute(route) : '页面浏览',
      detail: Number(v.loadingTimeMs) > 0 ? `${Math.round(Number(v.loadingTimeMs))}ms` : undefined,
      route,
      raw: v,
    });
  }

  for (const a of data.actions || []) {
    const route = String(a.route || '');
    items.push({
      id: String(a.eventId || `action-${items.length}`),
      at: Date.parse(String(a.timestamp || '')),
      kind: 'action',
      title: String(a.name || '交互操作'),
      detail: a.trigger ? String(a.trigger) : undefined,
      route,
      raw: a,
    });
  }

  for (const e of data.errors || []) {
    const presented = presentTimelineError(e);
    items.push({
      id: String(e.eventId || `error-${items.length}`),
      at: Date.parse(String(e.timestamp || '')),
      kind: 'error',
      title: presented.title,
      detail: presented.hint || undefined,
      route: presented.route || undefined,
      raw: e,
    });
  }

  for (const v of data.vitals || []) {
    const name = String(v.name || '').toUpperCase();
    const value = Number(v.value);
    const route = String(v.route || '');
    const formattedVal = name === 'CLS' ? value.toFixed(3) : Math.round(value);
    items.push({
      id: String(v.eventId || `vital-${items.length}`),
      at: Date.parse(String(v.timestamp || '')),
      kind: 'vital',
      title: `${name} ${formattedVal}${name !== 'CLS' ? 'ms' : ''}`,
      detail: v.rating ? String(v.rating) : undefined,
      route,
      raw: v,
    });
  }

  for (const n of data.network || []) {
    const route = String(n.route || '');
    items.push({
      id: String(n.eventId || `net-${items.length}`),
      at: Date.parse(String(n.timestamp || '')),
      kind: 'network',
      title: String(n.url || n.initiator || '网络请求'),
      detail: n.status ? String(n.status) : undefined,
      route,
      raw: n,
    });
  }

  for (const c of data.console || []) {
    const route = String(c.route || '');
    items.push({
      id: String(c.eventId || `con-${items.length}`),
      at: Date.parse(String(c.timestamp || '')),
      kind: 'console',
      title: String(c.message || c.level || '控制台日志'),
      detail: c.level ? String(c.level) : undefined,
      route,
      raw: c,
    });
  }

  return items.filter((i) => Number.isFinite(i.at)).sort((a, b) => a.at - b.at);
}

function formatEventTime(at: number): string {
  return new Date(at).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function formatRelativeOffset(at: number, baseAt: number): string {
  if (!baseAt || !at || at < baseAt) return '+0s';
  const sec = Math.max(0, Math.round((at - baseAt) / 1000));
  if (sec < 60) return `+${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `+${m}m ${s ? `${s}s` : ''}`;
}

function formatFullDateTime(ts: string | number | undefined): string {
  if (!ts) return '—';
  const d = new Date(ts);
  if (!Number.isFinite(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function SessionMetaRow({
  label,
  value,
  title,
  mono,
  copyText,
}: {
  label: ReactNode;
  value: ReactNode;
  title?: string;
  mono?: boolean;
  /** Full string for clipboard; shows a copy control next to truncated values. */
  copyText?: string;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    if (!copyText) return;
    void navigator.clipboard.writeText(copyText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="flex min-w-0 items-center justify-between gap-3 rounded-md bg-[var(--color-fill-1)]/35 px-3 py-2 transition-colors hover:bg-[var(--color-fill-1)]/60">
      <span className="flex shrink-0 items-center gap-1 whitespace-nowrap text-[11px] font-medium text-[var(--color-text-3)]">
        {label}
      </span>
      <div className="flex min-w-0 items-center justify-end gap-1.5">
        <span
          className={`max-w-[170px] truncate text-right text-xs font-medium text-[var(--color-text-1)] ${
            mono ? 'font-mono' : ''
          }`}
          title={title}
        >
          {value}
        </span>
        {copyText ? (
          <Tooltip title={copied ? t('common.copied', '已复制') : t('common.copy', '复制')}>
            <button
              type="button"
              onClick={handleCopy}
              className="inline-flex size-4 shrink-0 items-center justify-center rounded text-[var(--color-text-3)] transition-colors hover:text-[var(--color-primary)]"
              aria-label={t('common.copy', '复制')}
            >
              {copied ? (
                <CheckOutlined className="text-[10px] text-[var(--color-success)]" />
              ) : (
                <CopyOutlined className="text-[10px]" />
              )}
            </button>
          </Tooltip>
        ) : null}
      </div>
    </div>
  );
}

export default function SessionDetailPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const params = useParams<{ sessionId: string }>();
  const sessionId = decodeURIComponent(params.sessionId || '');
  const { range, application, searchParams } = useRumSearchParams();
  const app = application || searchParams.get('application') || '';
  const { getSession, getReplayManifest, authReady } = useRumQueries();

  const [journey, setJourney] = useState<RumSessionJourney | null>(null);
  const [manifest, setManifest] = useState<RumReplayManifest | null>(null);
  const [pending, setPending] = useState(true);
  const [tab, setTab] = useState<'activity' | 'network' | 'console'>('activity');
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      if (!sessionId || !app) {
        setPending(false);
        setJourney(null);
        return;
      }
      setPending(true);
      void Promise.all([
        getSession(sessionId, app, range),
        getReplayManifest(app, sessionId).catch(() => null),
      ])
        .then(([session, replay]) => {
          if (isCancelled()) return;
          setJourney(session);
          setManifest(replay);
        })
        .catch(() => {
          if (!isCancelled()) setJourney(null);
        })
        .finally(() => {
          if (!isCancelled()) setPending(false);
        });
    },
    [app, getReplayManifest, getSession, range, sessionId],
  );

  const session = journey?.session || null;
  const degrade = degradationReason(journey);
  const timeline = useMemo(() => (journey ? buildTimeline(journey) : []), [journey]);

  const baseTime = useMemo(() => {
    if (session?.startTime) {
      const parsed = Date.parse(session.startTime);
      if (Number.isFinite(parsed)) return parsed;
    }
    return timeline[0]?.at || 0;
  }, [session?.startTime, timeline]);

  // 按 tab 与所选步骤路由过滤
  const filtered = useMemo(() => {
    return timeline.filter((item) => {
      if (selectedRoute && item.route && item.route !== selectedRoute) {
        return false;
      }
      if (tab === 'network') return item.kind === 'network';
      if (tab === 'console') return item.kind === 'console';
      return item.kind === 'view' || item.kind === 'action' || item.kind === 'error' || item.kind === 'vital';
    });
  }, [timeline, tab, selectedRoute]);

  // 各 Tab 数量
  const counts = useMemo(() => {
    let activity = 0;
    let network = 0;
    let consoleCount = 0;
    for (const item of timeline) {
      if (item.kind === 'network') network++;
      else if (item.kind === 'console') consoleCount++;
      else activity++;
    }
    return { activity, network, console: consoleCount };
  }, [timeline]);

  const duration = useMemo(() => {
    if (session?.startTime && session?.endTime) {
      const s = Date.parse(session.startTime);
      const e = Date.parse(session.endTime);
      if (Number.isFinite(s) && Number.isFinite(e) && e >= s) {
        return e - s;
      }
    }
    return 0;
  }, [session?.endTime, session?.startTime]);

  const hasReplay = Boolean(session?.hasReplay || (manifest && manifest.state === 'ready'));

  const sortedViews = useMemo(() => {
    if (!journey?.views) return [];
    return journey.views.slice().sort((a, b) => {
      const ta = Date.parse(String(a.timestamp || ''));
      const tb = Date.parse(String(b.timestamp || ''));
      return ta - tb;
    });
  }, [journey?.views]);

  const handleCopySessionId = useCallback(() => {
    if (!sessionId) return;
    void navigator.clipboard.writeText(sessionId).then(() => {
      setCopied(true);
      void message.success(t('common.copied', '已复制会话 ID'));
      setTimeout(() => setCopied(false), 2000);
    });
  }, [sessionId, t]);

  const device = parseDevice(session?.userAgent || '');
  const browser = parseBrowser(session?.userAgent || '');

  const DeviceIcon = useMemo(() => {
    if (device === 'mobile') return MobileOutlined;
    if (device === 'tablet') return TabletOutlined;
    return LaptopOutlined;
  }, [device]);

  if (!app) {
    return (
      <Alert
        type="info"
        showIcon
        message={t('rum.sessions.missingApp', '缺少应用参数')}
        description={t('rum.sessions.missingAppHint', '请从会话列表进入详情。')}
        action={<RumBackButton onClick={() => router.push('/rum/sessions')} />}
      />
    );
  }

  const replayHref = `/rum/sessions/${encodeURIComponent(sessionId)}/replay?application=${encodeURIComponent(app)}`;

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-y-auto">
      {/* 顶部主标题栏 */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <RumDetailTitle
          title={
            <div className="flex items-center gap-2">
              <span
                className="font-mono text-base font-semibold text-[var(--color-text-1)]"
                title={sessionId}
              >
                {truncateMiddle(sessionId, 36)}
              </span>
              <Tooltip title={copied ? t('common.copied', '已复制') : t('common.copy', '复制完整 ID')}>
                <button
                  type="button"
                  onClick={handleCopySessionId}
                  className="inline-flex size-6 items-center justify-center rounded text-[var(--color-text-3)] transition-colors hover:bg-[var(--color-fill-1)] hover:text-[var(--color-text-1)]"
                  aria-label="copy-session-id"
                >
                  {copied ? <CheckOutlined className="text-[var(--color-success)]" /> : <CopyOutlined />}
                </button>
              </Tooltip>
            </div>
          }
          afterTitle={
            <div className="flex items-center gap-1.5">
              {session?.errorCount ? (
                <Tag color="error" className="m-0 border-0 font-medium">
                  {session.errorCount} {t('rum.sessions.errors', '错误')}
                </Tag>
              ) : (
                <Tag color="success" className="m-0 border-0 font-medium">
                  <CheckCircleOutlined className="mr-1" />
                  {t('rum.sessions.healthy', '正常')}
                </Tag>
              )}
              {hasReplay ? (
                <Tag color="processing" className="m-0 border-0 font-medium">
                  <VideoCameraOutlined className="mr-1" />
                  {t('rum.sessions.hasReplayTag', '含回放')}
                </Tag>
              ) : null}
            </div>
          }
          onBack={() => router.push('/rum/sessions')}
          subtitle={
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-[var(--color-text-3)]">
              <span className="font-medium text-[var(--color-text-2)]">{app}</span>
              {session?.entryRoute ? (
                <>
                  <span aria-hidden>·</span>
                  <span>
                    {t('rum.sessions.landingPage', '落地页')}:{' '}
                    <span className="font-mono text-[var(--color-text-2)]">{displayRoute(session.entryRoute)}</span>
                  </span>
                </>
              ) : null}
              {session?.startTime ? (
                <>
                  <span aria-hidden>·</span>
                  <span>{formatFullDateTime(session.startTime)}</span>
                </>
              ) : null}
            </div>
          }
        />

        {/* 右侧主操作区 */}
        <div className="flex flex-wrap items-center gap-2">
          {hasReplay ? (
            <Link href={replayHref}>
              <Button type="primary" icon={<PlayCircleOutlined />}>
                {t('rum.sessions.replay', '会话回放')}
              </Button>
            </Link>
          ) : null}
        </div>
      </div>

      {degrade ? <PipelineDegradedBanner reason={degrade} /> : null}

      {pending && !journey ? <RumSessionDetailSkeleton /> : null}

      {!pending && !session ? (
        <Empty description={t('rum.sessions.notFound', '未找到该会话')} />
      ) : null}

      {session ? (
        <>
          {/* 顶部4个对称量化指标 */}
          <RumMetricGrid
            cells={[
              {
                label: t('rum.sessions.viewsCount', '浏览'),
                value: String(session.viewCount),
                tone: session.viewCount > 0 ? 'info' : 'neutral',
              },
              {
                label: t('rum.sessions.actions', '操作'),
                value: String(journey?.actions?.length || session.actionCount || 0),
                tone: 'neutral',
              },
              {
                label: t('rum.sessions.errors', '错误'),
                value: String(session.errorCount),
                tone: session.errorCount > 0 ? 'danger' : 'success',
              },
              {
                label: t('rum.sessions.duration', '时长'),
                value: formatDurationMs(duration),
                tone: duration > 0 ? 'info' : 'neutral',
              },
            ]}
          />

          {/* 响应式左右分析区：左侧事件流（内嵌页面步骤） + 右侧上下文面板 */}
          <div className="flex min-w-0 flex-col items-start gap-4 lg:flex-row">
            {/* 左侧主要区域：事件时间线（内置流转阶段导轨，不再孤零零地横跨切断上下） */}
            <div className="flex min-w-0 flex-1 flex-col gap-4 w-full">
              <section className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
                {/* 栏头 */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <h2 className="m-0 text-[13px] font-semibold text-[var(--color-text-1)]">
                      {t('rum.sessions.timeline', '事件时间线')}
                    </h2>
                    {selectedRoute ? (
                      <Tag
                        closable
                        onClose={() => setSelectedRoute(null)}
                        className="m-0 bg-[var(--color-fill-2)] border-0 text-xs text-[var(--color-text-2)]"
                      >
                        {displayRoute(selectedRoute)}
                      </Tag>
                    ) : null}
                  </div>
                  <Segmented
                    size="small"
                    value={tab}
                    onChange={(value) => setTab(value as typeof tab)}
                    options={[
                      {
                        value: 'activity',
                        label: (
                          <span className="flex items-center gap-1.5">
                            <span>{t('rum.sessions.tabActivity', '活动')}</span>
                            <span className="text-[11px] tabular-nums text-[var(--color-text-3)]">
                              ({counts.activity})
                            </span>
                          </span>
                        ),
                      },
                      {
                        value: 'network',
                        label: (
                          <span className="flex items-center gap-1.5">
                            <span>{t('rum.sessions.tabNetwork', '网络')}</span>
                            <span className="text-[11px] tabular-nums text-[var(--color-text-3)]">
                              ({counts.network})
                            </span>
                          </span>
                        ),
                      },
                      {
                        value: 'console',
                        label: (
                          <span className="flex items-center gap-1.5">
                            <span>{t('rum.sessions.tabConsole', '控制台')}</span>
                            <span className="text-[11px] tabular-nums text-[var(--color-text-3)]">
                              ({counts.console})
                            </span>
                          </span>
                        ),
                      },
                    ]}
                  />
                </div>

                {/* 会话流转阶段（将原先不上不下的会话旅程融入时间线头部，作为自然的筛选阶段） */}
                {sortedViews.length > 0 ? (
                  <div className="border-b border-[var(--color-border-2)] bg-[var(--color-fill-1)]/50 px-3.5 py-2">
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[11px] font-medium text-[var(--color-text-3)]">
                          {t('rum.sessions.journeySteps', '页面流转阶段')}
                        </span>
                        <span className="inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] px-1.5 text-[10px] font-semibold tabular-nums text-[var(--color-primary)]">
                          {sortedViews.length}
                        </span>
                      </div>
                      {selectedRoute ? (
                        <button
                          type="button"
                          onClick={() => setSelectedRoute(null)}
                          className="text-[11px] text-[var(--color-primary)] hover:underline"
                        >
                          {t('rum.sessions.showAllEvents', '显示全部事件')}
                        </button>
                      ) : (
                        <span className="text-[11px] text-[var(--color-text-4)]">
                          {t('rum.sessions.clickToFilter', '点击阶段筛选事件')}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {sortedViews.map((view, index) => {
                        const rawRoute = String(view.route || view.viewName || 'view');
                        const route = displayRoute(rawRoute);
                        const loading = Number(view.loadingTimeMs) > 0 ? `${Math.round(Number(view.loadingTimeMs))}ms` : null;
                        const isSelected = selectedRoute === rawRoute;

                        return (
                          <div key={`${rawRoute}-${index}`} className="flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => setSelectedRoute(isSelected ? null : rawRoute)}
                              className={[
                                'group flex items-center gap-1.5 rounded border px-2 py-1 text-left transition-all',
                                isSelected
                                  ? 'border-[var(--color-primary)] bg-[var(--color-primary-light-1)] shadow-2xs'
                                  : 'border-[var(--color-border-2)] bg-[var(--color-bg)] hover:border-[var(--color-primary)] hover:bg-[var(--color-fill-1)]',
                              ].join(' ')}
                            >
                              <span
                                className={[
                                  'flex size-4 shrink-0 items-center justify-center rounded-full font-mono text-[10px] font-bold',
                                  isSelected
                                    ? 'bg-[var(--color-primary)] text-white'
                                    : 'bg-[var(--color-fill-2)] text-[var(--color-text-3)]',
                                ].join(' ')}
                              >
                                {index + 1}
                              </span>
                              <span
                                className={[
                                  'truncate font-mono text-xs font-semibold',
                                  isSelected ? 'text-[var(--color-primary)]' : 'text-[var(--color-text-1)]',
                                ].join(' ')}
                                title={rawRoute}
                              >
                                {route}
                              </span>
                              {loading ? (
                                <span className="font-mono text-[10px] tabular-nums text-[var(--color-text-3)]">
                                  {loading}
                                </span>
                              ) : null}
                            </button>
                            {index < sortedViews.length - 1 ? (
                              <RightOutlined className="text-[10px] text-[var(--color-text-4)] shrink-0" />
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : null}

                {/* 详细时间线流 */}
                <div className="p-4">
                  {filtered.length === 0 ? (
                    <Empty
                      description={
                        selectedRoute
                          ? t('rum.sessions.noEventsInRoute', '该页面下暂无此类事件')
                          : t('rum.sessions.timelineEmpty', '此会话暂无事件')
                      }
                    />
                  ) : (
                    <div className="relative pl-6 before:absolute before:bottom-3 before:left-2.5 before:top-3 before:w-px before:bg-[var(--color-border-2)]/60">
                      <div className="flex flex-col gap-3.5">
                        {filtered.map((item) => {
                          const relOffset = formatRelativeOffset(item.at, baseTime);
                          const absTime = formatEventTime(item.at);
                          const presentedError =
                            item.kind === 'error' ? presentTimelineError(item.raw) : null;
                          const errorHref =
                            presentedError?.fingerprint && app
                              ? `/rum/errors/detail?fingerprint=${encodeURIComponent(presentedError.fingerprint)}&application=${encodeURIComponent(app)}&range=${range}`
                              : null;

                          return (
                            <div key={item.id} className="group relative flex items-start gap-3">
                              {/* 节点图标徽标 */}
                              <div className="absolute -left-6 mt-1 flex size-5 items-center justify-center rounded-full bg-[var(--color-bg)] ring-4 ring-[var(--color-bg)]">
                                {item.kind === 'view' ? (
                                  <span className="flex size-3.5 items-center justify-center rounded-full bg-[var(--color-success)] text-[9px] text-white">
                                    <CompassOutlined />
                                  </span>
                                ) : item.kind === 'action' ? (
                                  <span className="flex size-3.5 items-center justify-center rounded-full bg-[var(--color-primary)] text-[9px] text-white">
                                    <InteractionOutlined />
                                  </span>
                                ) : item.kind === 'vital' ? (
                                  <span className="flex size-3.5 items-center justify-center rounded-full bg-[var(--theme-color-status-warning)] text-[9px] text-white">
                                    <DashboardOutlined />
                                  </span>
                                ) : item.kind === 'error' ? (
                                  <span className="flex size-3.5 items-center justify-center rounded-full bg-[var(--color-fail)] text-[9px] text-white">
                                    <ExclamationCircleOutlined />
                                  </span>
                                ) : item.kind === 'network' ? (
                                  <span className="flex size-3.5 items-center justify-center rounded-full bg-[var(--color-text-3)] text-[9px] text-white">
                                    <ApiOutlined />
                                  </span>
                                ) : (
                                  <span className="flex size-3.5 items-center justify-center rounded-full bg-[var(--color-fill-3)] text-[9px] text-[var(--color-text-2)]">
                                    <CodeOutlined />
                                  </span>
                                )}
                              </div>

                              {/* 卡片内容 */}
                              <div className="min-w-0 flex-1 rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-3 transition-colors hover:border-[var(--color-border-1)] hover:bg-[var(--color-fill-1)]">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <div className="flex items-center gap-2">
                                    <Tag
                                      className="m-0 border-0 font-medium uppercase text-[11px]"
                                      color={
                                        item.kind === 'error'
                                          ? 'error'
                                          : item.kind === 'vital'
                                            ? 'warning'
                                            : item.kind === 'view'
                                              ? 'success'
                                              : item.kind === 'action'
                                                ? 'processing'
                                                : 'default'
                                      }
                                    >
                                      {t(`rum.sessions.kind.${item.kind}`, item.kind)}
                                    </Tag>
                                    <span
                                      className="truncate font-mono text-sm font-semibold text-[var(--color-text-1)]"
                                      title={item.title}
                                    >
                                      {errorHref ? (
                                        <Link
                                          href={errorHref}
                                          className="hover:text-[var(--color-primary)] hover:underline"
                                          onClick={(e) => e.stopPropagation()}
                                        >
                                          {item.title}
                                        </Link>
                                      ) : (
                                        item.title
                                      )}
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-2 text-xs text-[var(--color-text-3)] font-mono tabular-nums">
                                    <span className="font-semibold text-[var(--color-text-2)]">{relOffset}</span>
                                    <span aria-hidden>·</span>
                                    <span>{absTime}</span>
                                  </div>
                                </div>

                                {/* 详细附加属性 */}
                                {item.kind === 'vital' && item.raw ? (
                                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                                    {(() => {
                                      const metricName = String(item.raw.name || '').toLowerCase();
                                      const val = Number(item.raw.value || 0);
                                      const tone = cwvTone(metricName, val);
                                      if (tone === 'neutral') return null;
                                      const toneLabel =
                                        tone === 'success'
                                          ? t('rum.cwv.good', '良好 (Good)')
                                          : tone === 'warning'
                                            ? t('rum.cwv.needsImprove', '需改进')
                                            : t('rum.cwv.poor', '较差 (Poor)');
                                      return (
                                        <Tag
                                          color={tone === 'success' ? 'success' : tone === 'warning' ? 'warning' : 'error'}
                                          className="m-0 border-0"
                                        >
                                          {toneLabel}
                                        </Tag>
                                      );
                                    })()}
                                    {item.route ? (
                                      <span className="text-[var(--color-text-3)] font-mono">
                                        {displayRoute(item.route)}
                                      </span>
                                    ) : null}
                                  </div>
                                ) : null}

                                {presentedError && (presentedError.hint || presentedError.traceId) ? (
                                  <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--color-text-3)]">
                                    {presentedError.hint ? (
                                      <span className="font-mono">{presentedError.hint}</span>
                                    ) : null}
                                    {presentedError.traceId ? (
                                      <span className="font-mono">Trace: {presentedError.traceId}</span>
                                    ) : null}
                                  </div>
                                ) : null}

                                {item.kind === 'network' && item.raw ? (
                                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                                    <Tag color={Number(item.raw.status) >= 400 ? 'error' : 'success'} className="m-0 border-0 font-mono">
                                      {String(item.raw.status || 200)}
                                    </Tag>
                                    <span className="font-mono text-[var(--color-text-3)] break-all">
                                      {String(item.raw.url || '')}
                                    </span>
                                  </div>
                                ) : null}

                                {item.kind === 'console' && item.raw ? (
                                  <div className="mt-2 rounded bg-[var(--color-fill-2)] p-2 font-mono text-xs text-[var(--color-text-2)] break-all">
                                    {String(item.raw.message || '')}
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </section>
            </div>

            {/* 右侧上下文信息栏：回放剧场卡片 + 客户端环境元信息 */}
            <div className="flex w-full min-w-0 shrink-0 flex-col gap-4 overflow-hidden lg:w-[320px] lg:max-w-[320px]">
              {/* 会话回放剧场入口卡片 */}
              <div className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
                <div className="border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
                  <h3 className="m-0 flex items-center justify-between text-[13px] font-semibold text-[var(--color-text-1)]">
                    <span>{t('rum.sessions.replay', '会话回放')}</span>
                    {hasReplay ? (
                      <span className="inline-flex items-center gap-1 text-xs font-normal text-[var(--color-success)]">
                        <span className="size-1.5 rounded-full bg-[var(--color-success)]" />
                        {t('rum.sessions.replayReady', '已就绪')}
                      </span>
                    ) : (
                      <span className="text-xs font-normal text-[var(--color-text-3)]">
                        {t('rum.sessions.replayNotAvailable', '未录制')}
                      </span>
                    )}
                  </h3>
                </div>

                <div className="p-3.5">
                  {hasReplay ? (
                    <div className="flex flex-col gap-3">
                      {/* 仿视频播放器预览框 */}
                      <Link
                        href={replayHref}
                        className="group relative flex aspect-video w-full flex-col items-center justify-center overflow-hidden rounded-md bg-slate-900 transition-all hover:ring-2 hover:ring-[var(--color-primary)]"
                      >
                        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
                        <PlayCircleFilled className="relative text-3xl text-white/80 transition-transform group-hover:scale-110 group-hover:text-white" />
                        <div className="absolute bottom-2 left-2.5 right-2.5 flex items-center justify-between text-[11px] text-white/80 font-mono">
                          <span>{app}</span>
                          <span>{formatDurationMs(duration)}</span>
                        </div>
                      </Link>

                      <Link href={replayHref}>
                        <Button type="primary" block icon={<PlayCircleOutlined />}>
                          {t('rum.sessions.watchReplay', '播放完整屏幕回放')}
                        </Button>
                      </Link>
                    </div>
                  ) : (
                    <div className="rounded-md bg-[var(--color-fill-1)]/35 p-3 text-center text-xs text-[var(--color-text-3)]">
                      <VideoCameraOutlined className="mb-1 text-base text-[var(--color-text-4)]" />
                      <p className="m-0">{t('rum.sessions.noReplayDesc', '当前会话未产生屏幕录像。')}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* 客户端与环境元信息 */}
              <div className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
                <div className="border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)]/35 px-4 py-2.5">
                  <h3 className="m-0 text-[13px] font-semibold text-[var(--color-text-1)]">
                    {t('rum.sessions.metadata', '环境与属性')}
                  </h3>
                </div>

                <div className="min-w-0 space-y-2 p-3 text-xs">
                  <SessionMetaRow
                    label={t('rum.sessions.user', '用户')}
                    mono
                    title={session.userId || undefined}
                    copyText={session.userId || undefined}
                    value={
                      session.userId
                        ? session.userId
                        : t('rum.sessions.anonymous', '匿名访客')
                    }
                  />
                  <SessionMetaRow
                    label={
                      <>
                        <EnvironmentOutlined />
                        <span>{t('rum.sessions.geo', '位置')}</span>
                      </>
                    }
                    value={
                      session.geoCountry || session.geoCity
                        ? `${session.geoCountry || ''}${session.geoCity ? ` · ${session.geoCity}` : ''}`
                        : '—'
                    }
                  />
                  <SessionMetaRow
                    label={
                      <>
                        <DeviceIcon />
                        <span>{t('rum.sessions.device', '设备')}</span>
                      </>
                    }
                    value={<span className="capitalize">{device}</span>}
                  />
                  <SessionMetaRow
                    label={t('rum.sessions.browser', '浏览器')}
                    value={browser}
                  />
                  <SessionMetaRow
                    label={t('rum.sessions.app', '应用')}
                    mono
                    title={session.application || app}
                    value={session.application || app}
                  />
                  <SessionMetaRow
                    label={t('rum.sessions.environment', '环境')}
                    mono
                    value={session.environment || 'production'}
                  />
                  <SessionMetaRow
                    label={t('rum.sessions.release', '版本')}
                    mono
                    title={session.release || undefined}
                    value={session.release || '—'}
                  />

                  {/* 时段 */}
                  <div className="flex flex-col gap-1.5 rounded-md bg-[var(--color-fill-1)]/35 p-3">
                    <span className="flex items-center gap-1 text-[11px] font-medium text-[var(--color-text-3)]">
                      <ClockCircleOutlined />
                      <span>{t('rum.sessions.timeSpan', '时段')}</span>
                    </span>
                    <div className="font-mono text-[11px] tabular-nums text-[var(--color-text-2)]">
                      <div>始: {formatFullDateTime(session.startTime)}</div>
                      <div>终: {formatFullDateTime(session.endTime)}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
