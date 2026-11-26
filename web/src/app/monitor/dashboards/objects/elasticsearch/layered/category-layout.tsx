'use client';

import { useCallback, useEffect, useRef, useState, type Key, type ReactNode } from 'react';
import { Tabs } from 'antd';
import useMonitorApi from '@/app/monitor/api';
import type { TimeValuesProps } from '@/app/monitor/types';
import { useLinkedHost } from '../../../shared/use-linked-host';
import { LinkedHostSegment } from '../../../shared/widgets/linked-host-segment';
import HostAlertDrawer from '../../host/layered/host-alert-drawer';
import EventsRail, { hostAlertRailEvents, type HostAlertRailEvent } from '../../host/layered/events-rail';
import { overviewHostAlertParams } from '../../host/layered/host-alert-list';
import { ProTimeWindowProvider } from '../../host/layered/pro-time-window';
import layered from '../../host/layered/layered.module.scss';
import type { EsTabId, EsView } from './assemble';
import { FocusCard, HeapCard, KpiCard, RankCard, spanClass, StatCard, TrendCard } from './board';

const HEALTH_COLOR = {
  green: 'var(--color-success)',
  yellow: 'var(--color-warning)',
  red: 'var(--color-fail)',
  unknown: 'var(--color-text-3)'
} as const;

function useContentWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width ?? 0;
      setWidth((prev) => (Math.abs(prev - next) < 1 ? prev : next));
    });
    observer.observe(node);
    setWidth(node.getBoundingClientRect().width);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col">
      <h2 className="mb-3 flex h-7 items-center text-[14px] font-semibold text-[var(--color-text-1)]">{title}</h2>
      {children}
    </section>
  );
}

function RetryBanner({ count, onRetry }: { count: number; onRetry: () => void }) {
  if (count < 3) return null;
  return (
    <div className="mb-4 flex h-10 items-center justify-between rounded-xl border border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 text-[13px] text-[var(--color-text-2)]">
      <span>有 {count} 张卡加载失败</span>
      <button type="button" className="text-[var(--color-primary)]" onClick={onRetry}>全部重试</button>
    </div>
  );
}

export function EsIdentityChip({ view }: { view: EsView }) {
  const pending = view.pending || view.healthLabel === '';
  return (
    <span className="inline-flex min-w-0 items-center gap-2 text-[12px]" data-es-identity="">
      {pending ? (
        <span className="inline-block h-4 w-24 animate-pulse rounded bg-[var(--color-fill-2)]" />
      ) : (
        <>
          <span data-es-health={view.healthTone} style={{ color: HEALTH_COLOR[view.healthTone] }}>
            {view.healthTone === 'unknown' ? '—' : view.healthLabel}
          </span>
          <span className="text-[var(--color-text-4)]" aria-hidden>·</span>
          <span data-es-collection={view.collectionLabel} className="text-[var(--color-text-3)]">
            {view.collectionLabel}
          </span>
        </>
      )}
    </span>
  );
}

export default function ElasticsearchCategoryLayout({
  instanceId,
  monitorObjectId,
  linkedNodeId,
  linkedIp,
  instanceLoading,
  timeValues,
  queryTimeRange,
  view,
  onAlertChange
}: {
  instanceId: Key;
  monitorObjectId: Key;
  linkedNodeId: string;
  linkedIp: string;
  instanceLoading: boolean;
  timeValues: TimeValuesProps;
  queryTimeRange: { startMs: number; endMs: number } | null;
  view: EsView;
  onAlertChange: (next: { count: number | null; pending: boolean }) => void;
}) {
  const { getMonitorAlert } = useMonitorApi();
  const instanceKey = String(instanceId || '');
  const [tab, setTab] = useState<EsTabId>('overview');
  const [alertOpen, setAlertOpen] = useState(false);
  const [alertRefreshKey, setAlertRefreshKey] = useState(0);
  const [events, setEvents] = useState<HostAlertRailEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(true);
  const { ref, width } = useContentWidth();
  const linked = useLinkedHost(linkedNodeId, linkedIp, !instanceLoading);
  const visibleTabs = view.tabs;
  const activeTab = visibleTabs.some((item) => item.id === tab) ? tab : 'overview';
  const retry = view.retry;

  const openAlerts = useCallback(() => {
    setAlertOpen(true);
    setAlertRefreshKey((key) => key + 1);
  }, []);

  const jump = useCallback((target: 'nodes' | 'queues') => {
    setTab(target);
    ref.current?.scrollIntoView({ block: 'start' });
  }, [ref]);

  useEffect(() => {
    setTab('overview');
    onAlertChange({ count: null, pending: true });
  }, [instanceKey, onAlertChange]);

  useEffect(() => {
    if (!instanceKey) {
      onAlertChange({ count: null, pending: false });
      setEvents([]);
      setEventsLoading(false);
      return undefined;
    }
    let active = true;
    onAlertChange({ count: null, pending: true });
    setEventsLoading(true);
    getMonitorAlert(overviewHostAlertParams(instanceKey))
      .then((data) => {
        if (!active) return;
        setEvents(hostAlertRailEvents(data?.results));
        setEventsLoading(false);
        onAlertChange({
          count: typeof data?.count === 'number' ? data.count : 0,
          pending: false
        });
      })
      .catch(() => {
        if (!active) return;
        setEvents([]);
        setEventsLoading(false);
        onAlertChange({ count: null, pending: false });
      });
    return () => {
      active = false;
    };
  }, [getMonitorAlert, instanceKey, onAlertChange]);

  const overviewErrors = [
    ...view.kpis,
    ...view.focuses,
    view.httpOpen,
    view.httpRate
  ].filter((card) => card.status === 'error').length;
  const nodeErrors = [view.heap, ...view.ranks, view.writeRate, view.gc].filter((card) => card.status === 'error').length;
  const queueErrors = [view.queueStat, view.breakerStat, view.queueTrend, view.breakerTrend]
    .filter((card) => card.status === 'error').length;
  const errorCount = activeTab === 'overview' ? overviewErrors : activeTab === 'nodes' ? nodeErrors : queueErrors;

  return (
    <ProTimeWindowProvider timeValues={timeValues} queryTimeRange={queryTimeRange} suspend={view.pending}>
      <div className={`${layered.root} @container`} ref={ref} data-es-pro="">
        <div className={layered.tabBand}>
          <Tabs
            className={layered.partitionTabs}
            activeKey={activeTab}
            onChange={(key) => setTab(key as EsTabId)}
            items={visibleTabs.map((item) => ({
              key: item.id,
              label: <span data-es-tab={item.id}>{item.title}</span>
            }))}
          />
        </div>
        <div className={`${layered.main} flex flex-col gap-6`}>
          <RetryBanner count={errorCount} onRetry={retry} />
          {activeTab === 'overview' ? (
            <>
              <Section title="健康概览">
                <div className="flex flex-col gap-4">
                  <div className="flex h-10 items-center rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] px-3" data-es-card="host">
                    <LinkedHostSegment
                      host={linked.host}
                      href={linked.href}
                      pending={instanceLoading || linked.pending}
                    />
                  </div>
                  <div className="grid grid-cols-12 gap-4">
                    {view.kpis.slice(0, 4).map((card) => (
                      <div key={card.id} className={spanClass('quarter', width)}>
                        <KpiCard card={card} onOpenAlerts={openAlerts} onRetry={retry} />
                      </div>
                    ))}
                  </div>
                  <div className="grid grid-cols-12 gap-4">
                    {view.kpis.slice(4).map((card) => (
                      <div key={card.id} className={spanClass('quarter', width)}>
                        <KpiCard card={card} onOpenAlerts={openAlerts} onRetry={retry} />
                      </div>
                    ))}
                  </div>
                  <div className="h-[72px] [&_[data-events-rail]]:h-full [&_[data-events-rail]]:min-h-[72px]" data-es-card="events">
                    <EventsRail events={events} loading={eventsLoading} onFocusAlert={() => openAlerts()} />
                  </div>
                  <div className="grid grid-cols-12 gap-4">
                    {view.focuses.map((card) => (
                      <div key={card.id} className={spanClass('third', width)}>
                        <FocusCard card={card} onOpen={jump} onRetry={retry} />
                      </div>
                    ))}
                  </div>
                </div>
              </Section>
              <Section title="连接趋势">
                <div className="grid grid-cols-12 gap-4">
                  <div className={spanClass('half', width)}><TrendCard card={view.httpOpen} onRetry={retry} /></div>
                  <div className={spanClass('half', width)}><TrendCard card={view.httpRate} onRetry={retry} /></div>
                </div>
              </Section>
            </>
          ) : null}
          {activeTab === 'nodes' ? (
            <>
              <Section title="内存">
                <HeapCard card={view.heap} onRetry={retry} />
              </Section>
              <Section title="节点排行">
                <div className="grid grid-cols-12 gap-4">
                  {view.ranks.map((card) => (
                    <div key={card.id} className={spanClass('quarter', width)}>
                      <RankCard card={card} onRetry={retry} />
                    </div>
                  ))}
                </div>
              </Section>
              <Section title="写入与回收">
                <div className="grid grid-cols-12 gap-4">
                  <div className={spanClass('half', width)}><TrendCard card={view.writeRate} onRetry={retry} /></div>
                  <div className={spanClass('half', width)}><TrendCard card={view.gc} onRetry={retry} /></div>
                </div>
              </Section>
            </>
          ) : null}
          {activeTab === 'queues' ? (
            <>
              <Section title="当前">
                <div className="grid grid-cols-12 gap-4">
                  <div className={spanClass('half', width)}><StatCard card={view.queueStat} onRetry={retry} /></div>
                  <div className={spanClass('half', width)}><StatCard card={view.breakerStat} onRetry={retry} /></div>
                </div>
              </Section>
              <Section title="趋势">
                <div className="grid grid-cols-12 gap-4">
                  <div className={spanClass('half', width)}><TrendCard card={view.queueTrend} onRetry={retry} /></div>
                  <div className={spanClass('half', width)}><TrendCard card={view.breakerTrend} onRetry={retry} /></div>
                </div>
              </Section>
            </>
          ) : null}
        </div>
        <HostAlertDrawer
          open={alertOpen}
          refreshKey={alertRefreshKey}
          instanceId={instanceKey}
          monitorObjectId={monitorObjectId}
          onClose={() => setAlertOpen(false)}
          onCount={(count) => onAlertChange({ count, pending: false })}
          title="告警"
          footerHint="当前对象尚未恢复的告警。"
          emptyCopy="当前无活跃告警"
          emptyHint="集群这条线上没有未恢复告警。"
        />
      </div>
    </ProTimeWindowProvider>
  );
}
