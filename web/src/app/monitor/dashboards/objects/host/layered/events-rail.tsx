'use client';

import React, { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Popover } from 'antd';
import { LEVEL_MAP } from '@/app/monitor/constants';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useDashboardText } from '../../../shared/utils/content-i18n';
import { alertEventInsideWindow } from '../../../shared/utils/pro-chart-window';
import { hostCategoryText } from './category-copy';
import { useProTimeWindow } from './pro-time-window';
import ProDashLoading from './pro-dash-loading';
import styles from './layered.module.scss';

export type HostAlertRailAction = 'triggered' | 'recovered' | 'closed';

export interface HostAlertRailEvent {
  id: string;
  alertId: string;
  at: string;
  action: HostAlertRailAction;
  level: string;
  status: string;
  summary: string;
  detail: string;
}

const ACTION_LABEL: Record<HostAlertRailAction, string> = {
  triggered: '触发',
  recovered: '恢复',
  closed: '关闭'
};

const CHIP_GAP = 8;
const RAIL_LIMIT = 24;

const asRecord = (value: unknown): Record<string, unknown> | null => {
  if (!value || typeof value !== 'object') return null;
  return value as Record<string, unknown>;
};

const textOf = (value: unknown) => (typeof value === 'string' ? value.trim() : '');

const idOf = (value: unknown) => {
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return textOf(value);
};

const timeOf = (value: unknown) => {
  const text = textOf(value);
  if (!text || !Number.isFinite(Date.parse(text))) return '';
  return text;
};

const collapse = (value: string) => value.replace(/\s+/g, ' ').trim();

const severityColor = (level: string) => {
  const raw = LEVEL_MAP[level];
  if (typeof raw === 'string') return raw;
  if (level === 'success') return 'var(--color-success)';
  if (level === 'info') return 'var(--color-primary)';
  return 'var(--color-text-3)';
};

/** 一条告警只保留触发，以及真实的恢复/关闭。没有时间的记录丢掉。 */
export function hostAlertRailEvents(rows: unknown): HostAlertRailEvent[] {
  if (!Array.isArray(rows)) return [];
  const events: HostAlertRailEvent[] = [];
  rows.forEach((raw, index) => {
    const row = asRecord(raw);
    if (!row) return;
    const alertId = idOf(row.id) || `alert-${index}`;
    const level = textOf(row.level);
    const content = collapse(textOf(row.content));
    const detail = content || (textOf(row.alert_type) === 'no_data' ? '无数据' : '');
    const byAction = new Map<HostAlertRailAction, string>();
    const openAt = timeOf(row.start_event_time) || timeOf(row.created_at);
    if (openAt) byAction.set('triggered', openAt);

    const logs = Array.isArray(row.operation_logs) ? row.operation_logs : [];
    logs.forEach((logRaw) => {
      const log = asRecord(logRaw);
      if (!log) return;
      const action = textOf(log.action);
      if (action !== 'recovered' && action !== 'closed') return;
      const at = timeOf(log.time);
      if (!at) return;
      const previous = byAction.get(action);
      if (!previous || Date.parse(at) >= Date.parse(previous)) byAction.set(action, at);
    });

    const status = textOf(row.status);
    if ((status === 'recovered' || status === 'closed') && !byAction.has(status)) {
      const at = timeOf(row.end_event_time) || timeOf(row.updated_at);
      if (at) byAction.set(status, at);
    }

    byAction.forEach((at, action) => {
      events.push({
        id: `${alertId}:${action}:${at}`,
        alertId,
        at,
        action,
        level,
        status,
        summary: detail,
        detail
      });
    });
  });
  events.sort((left, right) => Date.parse(right.at) - Date.parse(left.at) || right.id.localeCompare(left.id));
  return events.slice(0, RAIL_LIMIT);
}

/** 单行能放下的条数。放不下的留给「+N」。宽度尚未量到时先全部留下，避免空轨。 */
export function fitEventCount(widths: number[], available: number, moreWidth: number, gap = CHIP_GAP) {
  if (!widths.length) return 0;
  if (available <= 0 || widths.every((width) => width <= 0)) return widths.length;
  let used = 0;
  let count = 0;
  for (let index = 0; index < widths.length; index += 1) {
    const width = widths[index];
    const nextGap = count > 0 ? gap : 0;
    const hiddenAfter = widths.length - index - 1;
    const reserve = hiddenAfter > 0 ? moreWidth + gap : 0;
    if (used + nextGap + width + reserve > available) break;
    used += nextGap + width;
    count = index + 1;
  }
  return count === 0 ? 1 : count;
}

const EventBody = ({
  event,
  time
}: {
  event: HostAlertRailEvent;
  time: string;
}) => (
  <>
    <span className={styles.eventsDot} style={{ background: severityColor(event.level) }} />
    <span className={styles.eventsTime}>{time}</span>
    <span className={styles.eventsVerb}>{ACTION_LABEL[event.action]}</span>
    {event.summary ? <span className={styles.eventsText}>{event.summary}</span> : null}
  </>
);

export default function EventsRail({
  events,
  onFocusAlert,
  loading = false
}: {
  events: HostAlertRailEvent[];
  onFocusAlert?: (alertId: string) => void;
  loading?: boolean;
}) {
  const proTime = useProTimeWindow();
  const chartWindow = proTime?.window ?? null;
  const shownEvents = useMemo(
    () => events.filter((event) => alertEventInsideWindow(event.at, chartWindow)),
    [chartWindow, events]
  );
  const { convertToLocalizedTime } = useLocalizedTime();
  const { t } = useDashboardText();
  const rowRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const [visibleCount, setVisibleCount] = useState(events.length);
  const clock = useMemo(() => {
    const format = (iso: string, pattern: string) => {
      try {
        return convertToLocalizedTime(iso, pattern) || iso;
      } catch {
        return iso;
      }
    };
    return {
      short: (iso: string) => format(iso, 'HH:mm'),
      full: (iso: string) => format(iso, 'YYYY-MM-DD HH:mm:ss')
    };
  }, [convertToLocalizedTime]);

  useLayoutEffect(() => {
    const row = rowRef.current;
    const measure = measureRef.current;
    if (!row || !measure) return undefined;
    const update = () => {
      const chips = Array.from(measure.querySelectorAll<HTMLElement>('[data-event-chip]'));
      const more = measure.querySelector<HTMLElement>('[data-event-more]');
      const count = fitEventCount(
        chips.map((chip) => chip.offsetWidth),
        row.clientWidth,
        more?.offsetWidth ?? 0
      );
      setVisibleCount(count);
    };
    update();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(update);
    observer.observe(row);
    return () => observer.disconnect();
  }, [proTime?.suspend, shownEvents]);

  if (loading || proTime?.suspend) {
    return (
      <div className={styles.eventsRail} data-events-rail="" data-events-empty="" aria-busy="true">
        <div className={`${styles.eventsRow} w-full justify-center`}>
          <ProDashLoading layout="inline" />
        </div>
      </div>
    );
  }

  if (!shownEvents.length) {
    return (
      <div className={styles.eventsRail} data-events-rail="" data-events-empty="">
        <div className={styles.eventsRow}>
          <span className={styles.eventsEmpty}>{hostCategoryText(t, 'noEvents')}</span>
        </div>
      </div>
    );
  }

  const visible = shownEvents.slice(0, visibleCount);
  const hidden = shownEvents.slice(visibleCount);
  const focusable = (event: HostAlertRailEvent) => event.status === 'new' && Boolean(onFocusAlert);

  const detail = (event: HostAlertRailEvent) => (
    <div className={styles.eventsTip}>
      <div className={styles.eventsTipMeta}>
        <span className={styles.eventsDot} style={{ background: severityColor(event.level) }} />
        <span>{clock.full(event.at)}</span>
        <span>{ACTION_LABEL[event.action]}</span>
      </div>
      {event.detail ? <div className={styles.eventsTipBody}>{event.detail}</div> : null}
    </div>
  );

  return (
    <div className={styles.eventsRail} data-events-rail="">
      <div ref={measureRef} className={styles.eventsMeasure} aria-hidden="true">
        {shownEvents.map((event) => (
          <span key={event.id} data-event-chip="" className={styles.eventsChip}>
            <EventBody event={event} time={clock.short(event.at)} />
          </span>
        ))}
        <span data-event-more="" className={styles.eventsMore}>{`+${shownEvents.length}`}</span>
      </div>
      <div ref={rowRef} className={styles.eventsRow}>
        {visible.map((event) => {
          const chip = (
            <button
              type="button"
              className={styles.eventsChip}
              onClick={focusable(event) ? () => onFocusAlert?.(event.alertId) : undefined}
            >
              <EventBody event={event} time={clock.short(event.at)} />
            </button>
          );
          if (focusable(event)) return <React.Fragment key={event.id}>{chip}</React.Fragment>;
          return (
            <Popover key={event.id} trigger="click" placement="bottomLeft" content={detail(event)}>
              {chip}
            </Popover>
          );
        })}
        {hidden.length > 0 ? (
          <Popover
            trigger="click"
            placement="bottomRight"
            content={(
              <div className={styles.eventsOverflow}>
                {hidden.map((event) => (
                  <button
                    key={event.id}
                    type="button"
                    className={styles.eventsOverflowItem}
                    onClick={focusable(event) ? () => onFocusAlert?.(event.alertId) : undefined}
                  >
                    <EventBody event={event} time={clock.short(event.at)} />
                  </button>
                ))}
              </div>
            )}
          >
            <button type="button" className={styles.eventsMore}>{`+${hidden.length}`}</button>
          </Popover>
        ) : null}
      </div>
    </div>
  );
}
