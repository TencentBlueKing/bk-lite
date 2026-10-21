'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Drawer } from 'antd';
import { CheckOutlined } from '@ant-design/icons';
import useMonitorApi from '@/app/monitor/api';
import { LEVEL_MAP } from '@/app/monitor/constants';
import { useLevelList, useStateMap } from '@/app/monitor/hooks';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { formatRelativeTime } from '@/utils/relativeTime';
import {
  HOST_ALERT_PAGE_SIZE,
  activeHostAlertParams,
  isCanceledRequest,
  mergeHostAlerts,
  normalizeHostAlerts,
  readAlertCount,
  sortHostAlerts,
  type HostAlertRecord
} from './host-alert-list';

const DRAWER_WIDTH = 440;
const SKELETON_ROWS = 3;
const EMPTY_COPY = '当前无活跃告警';
const EMPTY_HINT = '本机运行正常';
const FAIL_COPY = '加载失败';
const RETRY_COPY = '重试';
const KNOWN_LEVELS = ['critical', 'error', 'warning'] as const;

interface HostAlertDrawerProps {
  open: boolean;
  refreshKey: number;
  instanceId?: string;
  monitorObjectId?: React.Key;
  focusAlertId?: string;
  onClose: () => void;
  onCount: (count: number) => void;
  title?: string;
  footerHint?: string;
  emptyCopy?: string;
  emptyHint?: string;
}

const levelColor = (level: string) => {
  const raw = LEVEL_MAP[level as keyof typeof LEVEL_MAP];
  return typeof raw === 'string' ? raw : 'var(--color-primary)';
};

const tonePaint = (level: string) => {
  const color = levelColor(level);
  return {
    bar: color,
    ink: `color-mix(in srgb, ${color} 72%, var(--color-text-1))`,
    wash: `color-mix(in srgb, ${color} 14%, var(--color-bg))`
  };
};

const clockOf = (
  value: string | null | undefined,
  format: (iso: string, pattern: string) => string
) => {
  if (!value || !Number.isFinite(Date.parse(value))) return '';
  const formatted = format(value, 'HH:mm');
  if (!formatted || formatted === 'Invalid Date') return '';
  return formatted;
};

export default function HostAlertDrawer({
  open,
  refreshKey,
  instanceId,
  monitorObjectId,
  focusAlertId = '',
  onClose,
  onCount,
  title = '本机告警',
  footerHint = '仅显示本机活跃告警',
  emptyCopy = EMPTY_COPY,
  emptyHint = EMPTY_HINT
}: HostAlertDrawerProps) {
  const { getMonitorAlert } = useMonitorApi();
  const levelList = useLevelList();
  const stateMap = useStateMap();
  const { convertToLocalizedTime } = useLocalizedTime();
  const onCountRef = useRef(onCount);
  const listRef = useRef<HTMLDivElement>(null);
  const appliedFocus = useRef('');
  const [attempt, setAttempt] = useState(0);
  const [rows, setRows] = useState<HostAlertRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [phase, setPhase] = useState<'idle' | 'ready' | 'empty' | 'error'>('idle');
  const [morePhase, setMorePhase] = useState<'idle' | 'loading' | 'error'>('idle');
  const [exhausted, setExhausted] = useState(false);
  const [expandedId, setExpandedId] = useState<string>('');
  const [settledSession, setSettledSession] = useState('');
  const session = `${refreshKey}:${attempt}:${instanceId || ''}`;
  const loading = open && settledSession !== session;

  onCountRef.current = onCount;

  useEffect(() => {
    if (!open) return undefined;
    listRef.current?.focus();
    const instance = String(instanceId || '').trim();
    if (!instance) {
      setRows([]);
      setTotal(0);
      setPage(1);
      setPhase('empty');
      setMorePhase('idle');
      setExhausted(false);
      setExpandedId('');
      setSettledSession(session);
      return undefined;
    }
    const controller = new AbortController();
    let active = true;
    setExpandedId('');
    setMorePhase('idle');
    setExhausted(false);
    getMonitorAlert(activeHostAlertParams(instance, 1, HOST_ALERT_PAGE_SIZE), {
      signal: controller.signal
    })
      .then((data) => {
        if (!active) return;
        const next = sortHostAlerts(normalizeHostAlerts(data?.results));
        const count = readAlertCount(data, next.length);
        setRows(next);
        setTotal(count);
        setPage(1);
        setPhase(next.length ? 'ready' : 'empty');
        setSettledSession(session);
        onCountRef.current(count);
      })
      .catch((error: unknown) => {
        if (!active || isCanceledRequest(error)) return;
        setPhase('error');
        setSettledSession(session);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [getMonitorAlert, instanceId, open, session]);

  useEffect(() => {
    if (!open || !focusAlertId || loading) return;
    const token = `${session}:${focusAlertId}`;
    if (appliedFocus.current === token) return;
    if (!rows.some((row) => String(row.id) === focusAlertId)) return;
    appliedFocus.current = token;
    setExpandedId(focusAlertId);
    const escaped = typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
      ? CSS.escape(focusAlertId)
      : focusAlertId.replace(/"/g, '');
    const node = listRef.current?.querySelector(`[data-host-alert-id="${escaped}"]`);
    if (node instanceof HTMLElement) node.scrollIntoView({ block: 'nearest' });
  }, [focusAlertId, loading, open, rows, session]);

  const loadMore = async () => {
    const instance = String(instanceId || '').trim();
    if (!instance || morePhase === 'loading') return;
    setMorePhase('loading');
    try {
      const data = await getMonitorAlert(activeHostAlertParams(instance, page + 1, HOST_ALERT_PAGE_SIZE));
      const incoming = normalizeHostAlerts(data?.results);
      if (!incoming.length) {
        setExhausted(true);
      } else {
        setRows((current) => mergeHostAlerts(current, incoming));
        setPage((current) => current + 1);
      }
      const count = readAlertCount(data, total);
      setTotal(count);
      onCountRef.current(count);
      setMorePhase('idle');
    } catch (error) {
      if (isCanceledRequest(error)) return;
      setMorePhase('error');
    }
  };

  const showBadge = !loading && (phase === 'ready' || phase === 'empty');
  const hasMore = phase === 'ready'
    && !exhausted
    && total > HOST_ALERT_PAGE_SIZE
    && rows.length < total;
  const objectId = typeof monitorObjectId === 'string' || typeof monitorObjectId === 'number'
    ? String(monitorObjectId)
    : '';
  const instanceFilter = String(instanceId || '').trim();
  const alertCenterParams = new URLSearchParams();
  if (objectId) alertCenterParams.set('objId', objectId);
  if (instanceFilter) alertCenterParams.set('instanceId', instanceFilter);
  const alertQuery = alertCenterParams.toString();
  const alertCenterHref = alertQuery
    ? `/monitor/event/alert?${alertQuery}`
    : '/monitor/event/alert';
  const absolute = (value?: string | null) => {
    if (!value) return '—';
    return convertToLocalizedTime(value) || '—';
  };
  const levelName = (level: string) => (
    levelList.find((item) => item.value === level)?.label || level
  );
  const summary = (() => {
    const counts = { critical: 0, error: 0, warning: 0, tip: 0 };
    rows.forEach((row) => {
      if (row.level === 'critical' || row.level === 'error' || row.level === 'warning') {
        counts[row.level] += 1;
      } else if (row.level) {
        counts.tip += 1;
      }
    });
    const items: Array<{ key: string; label: string; count: number; paint: ReturnType<typeof tonePaint> }> = KNOWN_LEVELS
      .filter((level) => counts[level] > 0)
      .map((level) => ({
        key: level,
        label: levelName(level),
        count: counts[level],
        paint: tonePaint(level)
      }));
    if (counts.tip > 0) {
      items.push({
        key: 'tip',
        label: '提示',
        count: counts.tip,
        paint: tonePaint('')
      });
    }
    return items;
  })();

  return (
    <Drawer
      title={(
        <span className="inline-flex items-center gap-2.5 text-[16px] font-semibold leading-6 text-[var(--color-text-1)]">
          {title}
          {showBadge ? (
            <span
              className={`inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[12px] font-semibold leading-none ${
                total > 0
                  ? 'bg-[var(--color-fail)] text-white'
                  : 'bg-[var(--color-text-3)] text-white'
              }`}
            >
              {total}
            </span>
          ) : null}
        </span>
      )}
      placement="right"
      width={DRAWER_WIDTH}
      open={open}
      onClose={onClose}
      maskClosable
      keyboard
      destroyOnClose={false}
      afterOpenChange={(visible) => {
        if (visible) listRef.current?.focus();
      }}
      styles={{
        header: {
          padding: '14px 20px 12px',
          borderBottom: '1px solid var(--color-border)',
          background: 'var(--color-bg)',
          flex: 'none'
        },
        content: {
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          overflow: 'hidden',
          background: 'var(--color-bg)'
        },
        body: {
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
          flex: '1 1 auto',
          minHeight: 0,
          overflow: 'hidden',
          background: 'var(--color-bg)'
        },
        footer: {
          padding: '12px 20px',
          borderTop: '1px solid var(--color-border)',
          background: 'var(--color-fill-1, #fafbfc)',
          flex: 'none'
        },
        wrapper: { maxWidth: 'min(440px, 100vw)' }
      }}
      footer={(
        <div className="flex items-center justify-between gap-3">
          {objectId || instanceFilter ? (
            <Link
              href={alertCenterHref}
              className="text-[13px] leading-5 text-[var(--color-primary)]"
            >
              在告警中心查看 →
            </Link>
          ) : <span />}
          <span className="shrink-0 text-[12px] leading-5 text-[var(--color-text-3)]">{footerHint}</span>
        </div>
      )}
    >
      <div
        ref={listRef}
        tabIndex={-1}
        aria-busy={loading}
        className="flex min-h-0 w-full flex-1 flex-col bg-[var(--color-bg)] outline-none"
      >
        {loading ? (
          <div className="flex flex-col gap-3 bg-[var(--color-bg)] px-4 py-3">
            {Array.from({ length: SKELETON_ROWS }, (_, index) => (
              <div
                key={index}
                className="flex h-16 items-stretch gap-3 rounded-lg border border-[var(--color-border)] py-2.5 pl-2.5 pr-3.5"
              >
                <span className="w-1 animate-neutral-pulse rounded-sm bg-[var(--color-fill-3)]" />
                <span className="flex min-w-0 flex-1 flex-col justify-center gap-2">
                  <span className="flex items-center gap-2">
                    <span className="h-3.5 flex-1 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" />
                    <span className="h-3 w-12 shrink-0 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" />
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="h-5 w-10 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" />
                    <span className="h-5 w-8 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" />
                    <span className="h-3 w-16 animate-neutral-pulse rounded bg-[var(--color-fill-2)]" />
                  </span>
                </span>
              </div>
            ))}
          </div>
        ) : null}
        {!loading && phase === 'error' ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
            <p className="m-0 text-[13px] text-[var(--color-text-2)]">{FAIL_COPY}</p>
            <button
              type="button"
              className="h-8 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-[13px] text-[var(--color-text-1)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]"
              onClick={() => setAttempt((current) => current + 1)}
            >
              {RETRY_COPY}
            </button>
          </div>
        ) : null}
        {!loading && phase === 'empty' ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
            <span
              className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--color-fill-2)] text-[22px] text-[var(--color-success)]"
              aria-hidden="true"
            >
              <CheckOutlined />
            </span>
            <span className="text-[13px] font-medium text-[var(--color-text-2)]">{emptyCopy}</span>
            <span className="text-[12px] text-[var(--color-text-3)]">{emptyHint}</span>
          </div>
        ) : null}
        {!loading && phase === 'ready' ? (
          <>
            {summary.length ? (
              <div className="flex shrink-0 flex-wrap gap-2 bg-[var(--color-bg)] px-5 pt-3">
                {summary.map((item) => (
                  <span
                    key={item.key}
                    className="inline-flex h-[26px] items-center gap-1.5 rounded-full px-2.5 text-[12px] leading-none"
                    style={{ background: item.paint.wash, color: item.paint.ink }}
                  >
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{ background: item.paint.bar }}
                      aria-hidden="true"
                    />
                    {item.label} {item.count}
                  </span>
                ))}
              </div>
            ) : null}
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto bg-[var(--color-bg)] px-4 py-3">
              {rows.map((row) => {
                const key = String(row.id);
                const expanded = expandedId === key;
                const title = row.content.trim() || '—';
                const relative = formatRelativeTime(row.updated_at || row.created_at || row.start_event_time) || '—';
                const strategy = row.policy?.name?.trim() || '';
                const statusLabel = (stateMap as Record<string, string>)[row.status] || '';
                const levelLabel = row.level
                  ? (levelList.some((item) => item.value === row.level) ? levelName(row.level) : '提示')
                  : '—';
                const firstClock = clockOf(
                  row.start_event_time || row.created_at,
                  convertToLocalizedTime
                );
                const meta = firstClock ? `首次 ${firstClock}` : strategy;
                const paint = tonePaint(row.level);
                return (
                  <div
                    key={key}
                    className="flex shrink-0 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] shadow-none transition-colors duration-150 hover:border-[color-mix(in_srgb,var(--color-primary)_32%,var(--color-border))]"
                  >
                    <span
                      className="pointer-events-none my-2.5 ml-2.5 w-1 shrink-0 self-stretch rounded-sm"
                      style={{ background: paint.bar }}
                      aria-hidden="true"
                    />
                    <div className="flex min-w-0 flex-1 flex-col pl-3 pr-3.5">
                      <button
                        type="button"
                        data-host-alert-id={key}
                        className="block w-full border-0 bg-transparent py-2.5 text-left font-[inherit]"
                        aria-expanded={expanded}
                        onClick={() => setExpandedId(expanded ? '' : key)}
                      >
                        <span className="flex items-start gap-2">
                          <span className="min-w-0 flex-1 truncate text-[13px] font-medium leading-[1.35] text-[var(--color-text-1)]" title={title}>
                            {title}
                          </span>
                          <span className="shrink-0 whitespace-nowrap text-[12px] leading-4 text-[var(--color-text-3)]">
                            {relative}
                          </span>
                        </span>
                        <span className="mt-2 flex flex-wrap items-center gap-1.5">
                          <span
                            className="inline-flex h-5 items-center rounded px-[7px] text-[11px] font-medium leading-none"
                            style={{ background: paint.wash, color: paint.ink }}
                          >
                            {levelLabel}
                          </span>
                          {statusLabel ? (
                            <span className="inline-flex h-5 items-center rounded bg-[color-mix(in_srgb,var(--color-primary)_12%,var(--color-bg))] px-[7px] text-[11px] font-medium leading-none text-[var(--color-primary)]">
                              {statusLabel}
                            </span>
                          ) : null}
                          {meta ? (
                            <span className="text-[11px] leading-4 text-[var(--color-text-3)]">{meta}</span>
                          ) : null}
                        </span>
                      </button>
                      {expanded ? (
                        <div className="mb-2.5 grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 rounded-md bg-[var(--color-fill-1)] px-3 py-2.5 text-[12px] leading-4">
                          <span className="text-[var(--color-text-3)]">级别</span>
                          <span className="text-[var(--color-text-1)]">{levelLabel}</span>
                          <span className="text-[var(--color-text-3)]">首次</span>
                          <span className="text-[var(--color-text-1)]">{absolute(row.start_event_time || row.created_at)}</span>
                          <span className="text-[var(--color-text-3)]">最近</span>
                          <span className="text-[var(--color-text-1)]">{absolute(row.updated_at || row.end_event_time)}</span>
                          <span className="text-[var(--color-text-3)]">策略</span>
                          <span className="truncate text-[var(--color-text-1)]">{strategy || '—'}</span>
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}
              {morePhase === 'error' ? (
                <button
                  type="button"
                  className="m-0 w-full border-0 bg-transparent py-2 text-[12px] text-[var(--color-primary)]"
                  onClick={loadMore}
                >
                  {FAIL_COPY}，{RETRY_COPY}
                </button>
              ) : null}
              {hasMore && morePhase !== 'error' ? (
                <button
                  type="button"
                  className="m-0 w-full border-0 bg-transparent py-2 text-[12px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]"
                  onClick={loadMore}
                  disabled={morePhase === 'loading'}
                >
                  {morePhase === 'loading' ? '加载中' : '加载更多'}
                </button>
              ) : null}
            </div>
          </>
        ) : null}
      </div>
    </Drawer>
  );
}
