'use client';

import { useCallback, useEffect, useState, type Key } from 'react';
import { Tabs } from 'antd';
import useMonitorApi from '@/app/monitor/api';
import type { TimeValuesProps } from '@/app/monitor/types';
import HostAlertDrawer from '../../host/layered/host-alert-drawer';
import { overviewHostAlertParams } from '../../host/layered/host-alert-list';
import { ProInfoHint, ProSection, proChromeClass } from '../../host/layered/pro-chrome';
import { ProTimeWindowProvider } from '../../host/layered/pro-time-window';
import layered from '../../host/layered/layered.module.scss';
import type { EsOverviewCard, EsTabId, EsView } from './assemble';
import { EsSeriesChart } from './series-chart';

const TONE_COLOR = {
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  fail: 'var(--color-fail)'
} as const;

const HEALTH_COLOR = {
  green: 'var(--color-success)',
  yellow: 'var(--color-warning)',
  red: 'var(--color-fail)',
  unknown: 'var(--color-text-3)'
} as const;

function CardHint({ card }: { card: EsOverviewCard }) {
  return (
    <ProInfoHint
      kind={`es-${card.id}`}
      label={`${card.hintTitle} ${card.hintBody}`}
      content={(
        <div className="max-w-[380px] whitespace-pre-line text-[13px] font-normal leading-[1.55] text-[var(--color-text-2)]">
          {card.hintBody}
        </div>
      )}
    />
  );
}

function OverviewGrid({
  cards,
  onOpenAlerts
}: {
  cards: readonly EsOverviewCard[];
  onOpenAlerts: () => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-7" data-es-overview="">
      {cards.map((card) => {
        const body = (
          <>
            <div className={`${proChromeClass.kpiLabel} inline-flex max-w-full items-center gap-1`}>
              <span className="min-w-0 truncate">{card.title}</span>
              <CardHint card={card} />
            </div>
            <div className={proChromeClass.kpiValue} style={card.tone ? { color: TONE_COLOR[card.tone] } : undefined}>
              {card.state === 'loading' ? <span className="inline-block h-5 w-16 animate-pulse rounded bg-[var(--color-fill-2)]" /> : card.value}
            </div>
            {card.note ? <div className="mt-1 max-w-full truncate text-[12px] text-[var(--color-text-3)]">{card.note}</div> : null}
          </>
        );
        if (card.opensAlerts) {
          return (
            <button
              key={card.id}
              type="button"
              className={proChromeClass.kpiCard}
              data-es-card={card.id}
              data-es-card-state={card.state}
              onClick={onOpenAlerts}
            >
              {body}
            </button>
          );
        }
        return (
          <div key={card.id} className={proChromeClass.kpiCard} data-es-card={card.id} data-es-card-state={card.state}>
            {body}
          </div>
        );
      })}
    </div>
  );
}

function ChartGrid({ charts, instanceKey }: { charts: EsView['nodes']; instanceKey: string }) {
  if (!charts.length) return null;
  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
      {charts.map((chart) => (
        <div key={`${instanceKey}:${chart.id}`} className={chart.lines.length > 3 ? 'xl:col-span-2' : undefined}>
          <EsSeriesChart key={`${instanceKey}:${chart.id}`} chart={chart} />
        </div>
      ))}
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
  timeValues,
  queryTimeRange,
  view,
  onAlertChange
}: {
  instanceId: Key;
  monitorObjectId: Key;
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
  const visibleTabs = view.tabs;
  const activeTab = visibleTabs.some((item) => item.id === tab) ? tab : 'overview';

  const openAlerts = useCallback(() => {
    setAlertOpen(true);
    setAlertRefreshKey((key) => key + 1);
  }, []);

  useEffect(() => {
    setTab('overview');
    onAlertChange({ count: null, pending: true });
  }, [instanceKey, onAlertChange]);

  useEffect(() => {
    if (!instanceKey) {
      onAlertChange({ count: null, pending: false });
      return undefined;
    }
    let active = true;
    onAlertChange({ count: null, pending: true });
    getMonitorAlert(overviewHostAlertParams(instanceKey))
      .then((data) => {
        if (!active) return;
        onAlertChange({
          count: typeof data?.count === 'number' ? data.count : 0,
          pending: false
        });
      })
      .catch(() => {
        if (!active) return;
        onAlertChange({ count: null, pending: false });
      });
    return () => {
      active = false;
    };
  }, [getMonitorAlert, instanceKey, onAlertChange]);

  const charts = activeTab === 'nodes'
    ? view.nodes
    : activeTab === 'throughput'
      ? view.throughput
      : activeTab === 'breakers'
        ? view.breakers
        : [];

  return (
    <ProTimeWindowProvider timeValues={timeValues} queryTimeRange={queryTimeRange} suspend={view.pending}>
      <div className={layered.root} data-es-pro="">
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
        <div className={layered.main}>
          {activeTab === 'overview' ? (
            <ProSection id="es-overview" title="健康概览">
              <OverviewGrid cards={view.overview} onOpenAlerts={openAlerts} />
            </ProSection>
          ) : (
            <ChartGrid charts={charts} instanceKey={instanceKey} />
          )}
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
