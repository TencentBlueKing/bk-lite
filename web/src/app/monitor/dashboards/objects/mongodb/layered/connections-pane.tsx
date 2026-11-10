'use client';

import { ProDashLoading, ProSection } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import classic from '../../host/index.module.scss';
import { ACTIVE_QUEUE_CHART, CONNECTION_TREND_CHART } from './chart-specs';
import { MongoHint } from './hint';
import { MongoTrend } from './trend';
import {
  connectionOccupancyNote,
  connectionOccupancyPercent,
  formatConnectionOccupancy,
  mongoLatest,
  type MongoMetricMap
} from './series';

const CURRENT_METRIC = 'mongodb_connections_current';
const AVAILABLE_METRIC = 'mongodb_connections_available';

const OCCUPANCY_BODY = '当前连接占可接纳上限的比例。\n当前连接 ÷（当前连接 + 尚可接纳连接）× 100%\n分母为 0 时显示 —，不用 0% 顶替。';

/** 与缓存使用率同一套左右卡：≥1100 左窄右宽，约 0.38fr : 1fr。更窄则上 KPI 下趋势。 */
const USAGE_PAIR_GRID = 'grid w-full min-w-0 grid-cols-1 items-stretch gap-3 min-[1100px]:min-h-[180px] min-[1100px]:grid-cols-[minmax(200px,0.38fr)_minmax(0,1fr)]';

function OccupancyCard({
  metricMap,
  pending
}: {
  metricMap: MongoMetricMap;
  pending: ReadonlySet<string>;
}) {
  const current = mongoLatest(metricMap, CURRENT_METRIC);
  const available = mongoLatest(metricMap, AVAILABLE_METRIC);
  const percent = connectionOccupancyPercent(current, available);
  const waiting = percent == null
    && (current == null || available == null)
    && (pending.has(CURRENT_METRIC) || pending.has(AVAILABLE_METRIC));
  const note = connectionOccupancyNote(current, available);
  const missing = !waiting && current == null && available == null;
  const state = waiting ? 'loading' : percent == null ? (missing ? 'missing' : 'denom') : 'ready';
  return (
    <section
      id="mongo-conn-usage"
      className={`${classic.panel} ${host.chartPanel} flex h-full min-w-0 flex-col`}
      data-mongodb-chart="conn-usage"
      data-mongodb-conn-usage={state}
    >
      <div className={host.chartHead}>
        <div className={host.chartTitle}>
          <span className="inline-flex items-center gap-1">
            连接占用率
            <MongoHint kind="mongo-conn-usage" title="连接占用率" body={OCCUPANCY_BODY} />
          </span>
        </div>
      </div>
      {waiting ? (
        <div className="flex flex-1 items-center justify-center">
          <ProDashLoading />
        </div>
      ) : (
        <div className="flex flex-1 flex-col justify-center">
          <div
            className="text-[30px] font-bold leading-none tabular-nums text-[var(--color-text-1)]"
            data-mongodb-conn-reading=""
          >
            {formatConnectionOccupancy(percent)}
          </div>
          {note ? (
            <p
              className="m-0 mt-3 text-[13px] leading-5 tabular-nums text-[var(--color-text-3)]"
              data-mongodb-conn-note=""
            >
              {note}
            </p>
          ) : missing ? (
            <p className="m-0 mt-3 text-[13px] leading-5 text-[var(--color-text-3)]">本窗口暂无数据</p>
          ) : null}
        </div>
      )}
    </section>
  );
}

export default function ConnectionsPane({
  metricMap,
  pendingMetricNames
}: {
  metricMap: MongoMetricMap;
  pendingMetricNames: ReadonlySet<string>;
}) {
  return (
    <div data-mongodb-pane="connections" className="contents">
      <ProSection title="连接">
        <div className="flex min-w-0 flex-col gap-3" data-mongodb-zone="connections">
          <div className={USAGE_PAIR_GRID} data-mongodb-connections-layout="usage-pair">
            <OccupancyCard metricMap={metricMap} pending={pendingMetricNames} />
            <MongoTrend
              stretch
              anchor={CONNECTION_TREND_CHART.anchor}
              title={CONNECTION_TREND_CHART.title}
              body={CONNECTION_TREND_CHART.body}
              series={CONNECTION_TREND_CHART.series}
              metricMap={metricMap}
              pending={pendingMetricNames}
            />
          </div>
          <div className={host.mongoChartCell} data-mongodb-zone="queue">
            <MongoTrend
              anchor={ACTIVE_QUEUE_CHART.anchor}
              title={ACTIVE_QUEUE_CHART.title}
              body={ACTIVE_QUEUE_CHART.body}
              series={ACTIVE_QUEUE_CHART.series}
              metricMap={metricMap}
              pending={pendingMetricNames}
              idleText={ACTIVE_QUEUE_CHART.idleText}
            />
          </div>
        </div>
      </ProSection>
    </div>
  );
}
