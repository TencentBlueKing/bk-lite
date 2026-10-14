'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Drawer } from 'antd';
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
const SKELETON_ROWS = 4;
const EMPTY_COPY = '当前无活跃告警';
const RETRY_COPY = '加载失败，点击重试';

interface HostAlertDrawerProps {
  open: boolean;
  refreshKey: number;
  instanceId?: string;
  monitorObjectId?: React.Key;
  onClose: () => void;
  onCount: (count: number) => void;
}

const levelColor = (level: string) => {
  const raw = LEVEL_MAP[level];
  return typeof raw === 'string' ? raw : 'var(--color-primary)';
};

export default function HostAlertDrawer({
  open,
  refreshKey,
  instanceId,
  monitorObjectId,
  onClose,
  onCount
}: HostAlertDrawerProps) {
  const { getMonitorAlert } = useMonitorApi();
  const levelList = useLevelList();
  const stateMap = useStateMap();
  const { convertToLocalizedTime } = useLocalizedTime();
  const onCountRef = useRef(onCount);
  const listRef = useRef<HTMLDivElement>(null);
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
  const absolute = (value?: string | null) => {
    if (!value) return '—';
    return convertToLocalizedTime(value) || '—';
  };

  return (
    <Drawer
      title={(
        <span className="inline-flex items-center gap-2 text-[14px] font-medium text-[var(--color-text-1)]">
          本机问题
          {showBadge ? (
            <span
              className={`inline-flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[11px] leading-none ${
                total > 0
                  ? 'bg-[var(--color-fail)] text-white'
                  : 'bg-[var(--color-fill-2)] text-[var(--color-text-2)]'
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
        body: { padding: 0, display: 'flex', flexDirection: 'column' },
        wrapper: { maxWidth: 'min(440px, 100vw)' }
      }}
      footer={objectId ? (
        <Link
          href={`/monitor/event/alert?objId=${encodeURIComponent(objectId)}`}
          className="text-[12px] leading-5 text-[var(--color-text-3)] hover:text-[var(--color-primary)]"
        >
          在告警中心查看
        </Link>
      ) : undefined}
    >
      <div
        ref={listRef}
        tabIndex={-1}
        aria-busy={loading}
        className="flex min-h-[240px] flex-1 flex-col outline-none"
      >
        {loading ? (
          <div>
            {Array.from({ length: SKELETON_ROWS }, (_, index) => (
              <div
                key={index}
                className="flex h-10 items-center gap-3 border-b border-[var(--color-border)] px-3"
              >
                <span className="h-6 w-[3px] animate-pulse rounded-sm bg-[var(--color-fill-3)]" />
                <span className="h-3 flex-1 animate-pulse rounded bg-[var(--color-fill-2)]" />
                <span className="h-3 w-12 animate-pulse rounded bg-[var(--color-fill-2)]" />
              </div>
            ))}
          </div>
        ) : null}
        {!loading && phase === 'error' ? (
          <button
            type="button"
            className="m-0 border-0 bg-transparent px-4 py-8 text-center text-[13px] text-[var(--color-primary)]"
            onClick={() => setAttempt((current) => current + 1)}
          >
            {RETRY_COPY}
          </button>
        ) : null}
        {!loading && phase === 'empty' ? (
          <div className="flex flex-1 items-center justify-center px-6 py-16 text-center text-[13px] text-[var(--color-text-3)]">
            {EMPTY_COPY}
          </div>
        ) : null}
        {!loading && phase === 'ready' ? (
          <div>
            {rows.map((row) => {
              const key = String(row.id);
              const expanded = expandedId === key;
              const title = row.content.trim() || '—';
              const relative = formatRelativeTime(row.updated_at || row.created_at || row.start_event_time) || '—';
              const strategy = row.policy?.name?.trim() || '';
              const statusLabel = (stateMap as Record<string, string>)[row.status] || '';
              const secondary = [strategy, statusLabel].filter(Boolean).join(' · ');
              const levelLabel = levelList.find((item) => item.value === row.level)?.label || row.level || '—';
              return (
                <div key={key} className="border-b border-[var(--color-border)]">
                  <button
                    type="button"
                    className="relative flex h-10 w-full items-center gap-2 overflow-hidden border-0 bg-transparent px-3 pl-4 text-left hover:bg-[var(--color-fill-1)]"
                    aria-expanded={expanded}
                    onClick={() => setExpandedId(expanded ? '' : key)}
                  >
                    <span
                      className="absolute bottom-0 left-0 top-0 w-[3px]"
                      style={{ background: levelColor(row.level) }}
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline gap-2">
                        <span className="min-w-0 flex-1 truncate text-[13px] leading-4 text-[var(--color-text-1)]" title={title}>
                          {title}
                        </span>
                        <span className="shrink-0 text-[12px] leading-4 text-[var(--color-text-3)]">
                          {relative}
                        </span>
                      </span>
                      {secondary ? (
                        <span className="block truncate text-[11px] leading-[14px] text-[var(--color-text-3)]">
                          {secondary}
                        </span>
                      ) : null}
                    </span>
                  </button>
                  {expanded ? (
                    <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 bg-[var(--color-fill-1)] px-4 py-2 text-[12px] leading-4">
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
              );
            })}
            {morePhase === 'error' ? (
              <button
                type="button"
                className="m-0 w-full border-0 bg-transparent py-2 text-[12px] text-[var(--color-primary)]"
                onClick={loadMore}
              >
                {RETRY_COPY}
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
        ) : null}
      </div>
    </Drawer>
  );
}
