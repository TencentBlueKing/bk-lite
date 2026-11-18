'use client';

import React, { useMemo } from 'react';
import type { MetricUnit } from '../../../shared/types';
import {
  EVENT_RAIL_HINT_LINES,
  KpiTileRow,
  ProDashLoading,
  ProFocusCard,
  ProInfoHint,
  ProSection,
  ThinTimeSeries,
  proChromeClass,
  type KpiTileModel
} from '../../host/layered/pro-chrome';
import EventsRail, { type HostAlertRailEvent } from '../../host/layered/events-rail';
import FocusShortcutTitle from '../../host/layered/focus-shortcut-title';
import { describeFocusAxis, formatFocusHeadline, seriesSampleValues } from '../../host/layered/focus-axis';
import host from '../../host/layered/layered.module.scss';
import { MssqlHint } from './hint';
import { mssqlFocusJump, mssqlKpiJump } from './ia';
import { MSSQL_PRO_NAMES, MSSQL_PRO_PALETTE } from './queries';
import {
  formatCount,
  formatMssqlUptime,
  formatPercentPoint,
  joinMetric,
  mssqlCountAxisBounds,
  mssqlCountMerged,
  mssqlLatest,
  mssqlMerged,
  mssqlPoints,
  mssqlWindowCount,
  type MssqlMetricMap
} from './series';
import { mssqlDeferEmpty } from './card-face';
import { mssqlLockedReading } from './display-units';
import { MssqlTrend } from './trend';

const EMPTY = '—';

const HIT_BODY = '缓冲池满足的数据页读取占比。偏低说明热点数据未充分驻留内存、读盘偏多。\n命中 ÷（命中 + 未命中）× 100%\n分母为 0 时显示 —，不用 0% 顶替。';
const DEADLOCK_BODY = '当前时间范围内发生的死锁次数。偶发需关注冲突会话；持续出现应排查锁顺序与长事务。暂无数据时显示 —。';

interface OverviewPaneProps {
  metricMap: MssqlMetricMap;
  pendingMetricNames: ReadonlySet<string>;
  booting: boolean;
  /** 同一批指标查询还没结束。没有读数的卡先保持加载中。 */
  batchLoading?: boolean;
  alertCount: number | null;
  alertsOpen: boolean;
  alertEvents: HostAlertRailEvent[];
  onOpenAlerts: () => void;
  onOpenFocus: (anchor: string) => void;
  onFocusAlert: (alertId: string) => void;
}

const alertValue = (count: number | null) => {
  if (count == null || !Number.isFinite(count)) return '--';
  return formatCount(Math.max(0, count), '个');
};

const alertTone = (count: number | null) => {
  if (count == null || !Number.isFinite(count)) return undefined;
  return count > 0 ? 'var(--color-fail)' : 'var(--color-success)';
};

const quiet = (latest: number | null, samples: readonly number[]) => (
  latest === 0 && samples.length > 0 && samples.every((value) => value === 0)
);

export default function OverviewPane({
  metricMap,
  pendingMetricNames,
  booting,
  batchLoading = false,
  alertCount,
  alertsOpen,
  alertEvents,
  onOpenAlerts,
  onOpenFocus,
  onFocusAlert
}: OverviewPaneProps) {
  const hit = mssqlLatest(metricMap, MSSQL_PRO_NAMES.hit);
  const connections = mssqlLatest(metricMap, MSSQL_PRO_NAMES.connections);
  const batch = mssqlLatest(metricMap, MSSQL_PRO_NAMES.batch);
  const cpu = mssqlLatest(metricMap, MSSQL_PRO_NAMES.processCpu);
  const uptime = formatMssqlUptime(mssqlLatest(metricMap, MSSQL_PRO_NAMES.uptime));

  const holdEmpty = (name: string, present: boolean) => mssqlDeferEmpty(
    present,
    booting || pendingMetricNames.has(name),
    batchLoading
  );
  const cards = useMemo<KpiTileModel[]>(() => {
    const jump = (key: string) => {
      const target = mssqlKpiJump(key);
      return target
        ? { onActivate: () => onOpenFocus(target.anchor), activatesDialog: false as const }
        : {};
    };
    const metricCards: KpiTileModel[] = [
      {
        key: 'connections',
        label: '用户连接数',
        value: connections == null ? EMPTY : formatCount(connections, '个'),
        busy: holdEmpty(MSSQL_PRO_NAMES.connections, connections != null),
        tone: connections == null ? undefined : MSSQL_PRO_PALETTE.indigo,
        info: <MssqlHint kind="mssql-kpi-connections" title="用户连接数" body="当前连到本实例的用户会话个数。" />,
        ...jump('connections')
      },
      {
        key: 'batch',
        label: '批处理请求速率',
        value: batch == null ? EMPTY : joinMetric(batch, 'cps'),
        busy: holdEmpty(MSSQL_PRO_NAMES.batch, batch != null),
        tone: batch == null ? undefined : MSSQL_PRO_PALETTE.emerald,
        info: <MssqlHint kind="mssql-kpi-batch" title="批处理请求速率" body="每秒完成的批处理请求数，反映实例的请求繁忙程度。" />,
        ...jump('batch')
      },
      {
        key: 'hit',
        label: '缓冲池命中率',
        value: hit == null ? EMPTY : formatPercentPoint(hit),
        busy: holdEmpty(MSSQL_PRO_NAMES.hit, hit != null),
        tone: hit == null ? undefined : MSSQL_PRO_PALETTE.emerald,
        info: <MssqlHint kind="mssql-kpi-hit" title="缓冲池命中率" body={HIT_BODY} />,
        ...jump('hit')
      },
      {
        key: 'cpu',
        label: '进程 CPU',
        value: cpu == null ? EMPTY : formatPercentPoint(cpu),
        busy: holdEmpty(MSSQL_PRO_NAMES.processCpu, cpu != null),
        tone: cpu == null ? undefined : MSSQL_PRO_PALETTE.blue,
        info: <MssqlHint kind="mssql-kpi-cpu" title="进程 CPU" body="SQL Server 进程自身占用的计算资源比例，按近 5 分钟平均。与整机 CPU 不是同一口径。" />,
        ...jump('cpu')
      },
      {
        key: 'uptime',
        label: '运行时间',
        value: uptime ?? EMPTY,
        busy: holdEmpty(MSSQL_PRO_NAMES.uptime, uptime != null),
        tone: uptime == null ? undefined : MSSQL_PRO_PALETTE.indigo,
        info: <MssqlHint kind="mssql-kpi-uptime" title="运行时间" body="实例自上次启动以来已持续运行的时间。" />
      },
      {
        key: 'alert-count',
        label: '告警数量',
        value: alertValue(alertCount),
        tone: alertTone(alertCount),
        info: <MssqlHint kind="mssql-kpi-alerts" title="告警数量" body="当前实例的活跃告警数。无告警时显示 0。" />,
        onActivate: onOpenAlerts,
        expanded: alertsOpen
      }
    ];
    return metricCards;
  }, [alertCount, alertsOpen, batch, batchLoading, booting, connections, cpu, hit, onOpenAlerts, onOpenFocus, pendingMetricNames, uptime]);

  return (
    <div data-mssql-pane="overview" className="contents">
      <ProSection title="健康概览">
        <KpiTileRow items={cards} columns={6} />
      </ProSection>
      {(alertCount ?? 0) > 0 ? (
        <ProSection title="事件" hint={<ProInfoHint kind="events" lines={EVENT_RAIL_HINT_LINES} />}>
          <EventsRail events={alertEvents} clipToWindow={false} onFocusAlert={onFocusAlert} />
        </ProSection>
      ) : null}
      <ProSection title="重点关注">
        <div className={proChromeClass.shortcutGrid} data-mssql-focus="grid">
          <FocusCard
            cardKey="read-latency"
            label="数据库读取延迟"
            body="数据库文件完成一次读取平均所需的时间。升高通常表示存储读路径变慢。"
            metric={MSSQL_PRO_NAMES.readLatency}
            unit="ms"
            color={MSSQL_PRO_PALETTE.blue}
            cta="查看读写延迟"
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
            onOpen={onOpenFocus}
          />
          <FocusCard
            cardKey="ple"
            label="页生命周期期望"
            body="数据页在缓冲池中预计可停留的时间。明显变短通常意味着内存压力上升。"
            metric={MSSQL_PRO_NAMES.pageLife}
            unit="s"
            color={MSSQL_PRO_PALETTE.cyan}
            cta="查看页寿命"
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
            onOpen={onOpenFocus}
          />
          <CountFocusCard
            cardKey="blocked"
            label="阻塞进程数"
            body="当前被其他会话堵住、正在等待的进程个数。"
            metric={MSSQL_PRO_NAMES.blocked}
            unitWord="个"
            color={MSSQL_PRO_PALETTE.rose}
            cta="查看锁与阻塞"
            windowTotal={false}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
            onOpen={onOpenFocus}
          />
          <CountFocusCard
            cardKey="deadlocks"
            label="死锁次数"
            body={DEADLOCK_BODY}
            metric={MSSQL_PRO_NAMES.deadlocks}
            unitWord="次"
            color={MSSQL_PRO_PALETTE.rose}
            cta="查看死锁次数"
            windowTotal
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
            onOpen={onOpenFocus}
          />
        </div>
      </ProSection>
      <ProSection title="趋势">
        <div className={host.chartGrid3}>
          <MssqlTrend
            anchor="connections"
            title="用户连接数"
            body="当前连到本实例的用户会话个数随时间的变化。"
            series={[{
              name: MSSQL_PRO_NAMES.connections,
              label: '用户连接数',
              color: MSSQL_PRO_PALETTE.indigo,
              unit: 'counts'
            }]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
            counts
          />
          <MssqlTrend
            anchor="batch"
            title="批处理请求速率"
            body="每秒完成的批处理请求数随时间的变化。"
            series={[{
              name: MSSQL_PRO_NAMES.batch,
              label: '批处理请求速率',
              color: MSSQL_PRO_PALETTE.emerald,
              unit: 'cps'
            }]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
          <MssqlTrend
            anchor="cpu"
            title="进程 CPU"
            body="SQL Server 进程自身占用的计算资源比例（近 5 分钟平均）。系统空闲 CPU 仅作对照。"
            percent
            series={[
              {
                name: MSSQL_PRO_NAMES.processCpu,
                label: '进程 CPU',
                color: MSSQL_PRO_PALETTE.blue,
                unit: 'percent'
              },
              {
                name: MSSQL_PRO_NAMES.idleCpu,
                label: '系统空闲',
                color: MSSQL_PRO_PALETTE.neutral,
                unit: 'percent',
                dashed: true
              }
            ]}
            metricMap={metricMap}
            pending={pendingMetricNames}
            batchLoading={batchLoading}
          />
        </div>
      </ProSection>
    </div>
  );
}

function FocusCard({
  cardKey,
  label,
  body,
  metric,
  unit,
  color,
  cta,
  metricMap,
  pending,
  batchLoading,
  onOpen
}: {
  cardKey: string;
  label: string;
  body: string;
  metric: string;
  unit: MetricUnit;
  color: string;
  cta: string;
  metricMap: MssqlMetricMap;
  pending: ReadonlySet<string>;
  batchLoading: boolean;
  onOpen: (anchor: string) => void;
}) {
  const plotted = mssqlMerged(metricMap, [{ name: metric, label }]);
  const latest = mssqlLatest(metricMap, metric);
  const samples = seriesSampleValues(plotted);
  const loading = mssqlDeferEmpty(
    plotted.length > 0 || latest != null,
    pending.has(metric),
    batchLoading
  );
  const peak = samples.reduce((max, value) => Math.max(max, Math.abs(value)), 0);
  const duration = unit === 'ms' ? mssqlLockedReading('ms', peak) : null;
  const axis = describeFocusAxis(unit, samples);
  const target = mssqlFocusJump(cardKey);
  return (
    <ProFocusCard>
      <div
        className={proChromeClass.shortcutCopy}
        data-mssql-focus={cardKey}
        data-mssql-face={loading ? 'loading' : latest == null ? 'empty' : 'ready'}
      >
        <FocusShortcutTitle
          label={label}
          unit={duration ? undefined : axis.unitLabel}
          hint={<MssqlHint kind={`mssql-focus-${cardKey}`} title={label} body={body} />}
        />
        {loading ? <ProDashLoading size="small" /> : (
          <div className={proChromeClass.shortcutValue} style={latest == null ? undefined : { color }}>
            {latest == null ? EMPTY : duration ? duration(latest) : formatFocusHeadline(axis, latest)}
          </div>
        )}
        {target ? (
          <button type="button" className={proChromeClass.jumpBtn} onClick={() => onOpen(target.anchor)}>
            {cta}
          </button>
        ) : null}
      </div>
      {plotted.length > 0 ? (
        <ThinTimeSeries
          bare
          numericAxis
          pinAxisZero
          className={proChromeClass.focusChart}
          title=""
          unit={unit}
          data={plotted}
          legends={[{ label, color }]}
          formatReading={duration ?? undefined}
        />
      ) : (
        <div className={proChromeClass.focusChart} />
      )}
    </ProFocusCard>
  );
}

function CountFocusCard({
  cardKey,
  label,
  body,
  metric,
  unitWord,
  color,
  cta,
  windowTotal,
  metricMap,
  pending,
  batchLoading,
  onOpen
}: {
  cardKey: string;
  label: string;
  body: string;
  metric: string;
  unitWord: '个' | '次';
  color: string;
  cta: string;
  windowTotal: boolean;
  metricMap: MssqlMetricMap;
  pending: ReadonlySet<string>;
  batchLoading: boolean;
  onOpen: (anchor: string) => void;
}) {
  const plotted = mssqlCountMerged(metricMap, [{ name: metric, label }]);
  const hasPoints = mssqlPoints(metricMap, metric).length > 0;
  const shown = plotted.filter((point) => typeof point.value1 === 'number');
  const latest = windowTotal
    ? (hasPoints ? mssqlWindowCount(metricMap, metric) : null)
    : mssqlLatest(metricMap, metric);
  const samples = seriesSampleValues(shown);
  const countBounds = mssqlCountAxisBounds(samples);
  const softened = quiet(windowTotal ? (samples.every((value) => value === 0) ? 0 : latest) : latest, samples);
  const loading = mssqlDeferEmpty(hasPoints, pending.has(metric), batchLoading);
  const target = mssqlFocusJump(cardKey);
  return (
    <ProFocusCard>
      <div
        className={proChromeClass.shortcutCopy}
        data-mssql-focus={cardKey}
        data-mssql-focus-weight={softened ? 'quiet' : 'normal'}
        data-mssql-face={loading ? 'loading' : latest == null ? 'empty' : 'ready'}
      >
        <FocusShortcutTitle
          label={label}
          unit={unitWord}
          hint={<MssqlHint kind={`mssql-focus-${cardKey}`} title={label} body={body} />}
        />
        {loading ? <ProDashLoading size="small" /> : (
          <div
            className={proChromeClass.shortcutValue}
            style={latest == null ? undefined : {
              color: latest > 0 ? color : undefined,
              ...(softened ? { fontSize: 15, fontWeight: 500 } : {})
            }}
          >
            {latest == null ? EMPTY : formatCount(latest, unitWord)}
          </div>
        )}
        {target ? (
          <button type="button" className={proChromeClass.jumpBtn} onClick={() => onOpen(target.anchor)}>
            {cta}
          </button>
        ) : null}
      </div>
      {hasPoints ? (
        <ThinTimeSeries
          bare
          numericAxis
          pinAxisZero
          markZeroCount={Boolean(countBounds)}
          keepSeriesColor={Boolean(countBounds)}
          resolveValueBounds={countBounds ? () => countBounds : undefined}
          className={proChromeClass.focusChart}
          title=""
          unit="counts"
          data={shown}
          legends={[{ label, color }]}
        />
      ) : (
        <div className={proChromeClass.focusChart} />
      )}
    </ProFocusCard>
  );
}
