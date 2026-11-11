'use client';

import { ProDashLoading, ProSection } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import classic from '../../host/index.module.scss';
import { useProTimeWindow } from '../../host/layered/pro-time-window';
import { ACTIVE_QUEUE_CHART, CONNECTION_TREND_CHART, NETWORK_CHARTS } from './chart-specs';
import { MongoHint } from './hint';
import { MongoTrend } from './trend';
import {
  connectionCap,
  formatMongoReading,
  mongoLatest,
  type MongoMetricMap
} from './series';

const CURRENT_METRIC = 'mongodb_connections_current';
const OPEN_METRIC = 'mongodb_open_connections';
const AVAILABLE_METRIC = 'mongodb_connections_available';

const CURRENT_BODY = '此刻连到本实例的客户端连接数。旁注为打开连接与可接纳上限。';

/** 与缓存使用率同一套左右卡：≥1100 左窄右宽，约 0.38fr : 1fr。更窄则上 KPI 下趋势。 */
const USAGE_PAIR_GRID = 'grid w-full min-w-0 grid-cols-1 items-stretch gap-3 min-[1100px]:min-h-[180px] min-[1100px]:grid-cols-[minmax(200px,0.38fr)_minmax(0,1fr)]';

function CurrentConnectionsCard({
  metricMap,
  pending
}: {
  metricMap: MongoMetricMap;
  pending: ReadonlySet<string>;
}) {
  const proTime = useProTimeWindow();
  const current = mongoLatest(metricMap, CURRENT_METRIC);
  const opened = mongoLatest(metricMap, OPEN_METRIC);
  const cap = connectionCap(current, mongoLatest(metricMap, AVAILABLE_METRIC));
  const waiting = current == null && (
    pending.has(CURRENT_METRIC) || Boolean(proTime?.suspend)
  );
  const openText = opened == null ? '' : formatMongoReading(opened, 'counts');
  const capText = cap == null ? '' : formatMongoReading(cap, 'counts');
  const state = waiting ? 'loading' : current == null ? 'missing' : 'ready';
  return (
    <section
      id="mongo-current-connections"
      className={`${classic.panel} ${host.chartPanel} flex h-full min-w-0 flex-col`}
      data-mongodb-chart="current-connections"
      data-mongodb-conn-state={state}
    >
      <div className={host.chartHead}>
        <div className={host.chartTitle}>
          <span className="inline-flex items-center gap-1">
            当前连接
            <MongoHint kind="mongo-current-connections" title="当前连接" body={CURRENT_BODY} />
          </span>
        </div>
      </div>
      {waiting ? (
        <div className="flex flex-1 items-center justify-center">
          <ProDashLoading />
        </div>
      ) : current == null ? (
        <div className="flex flex-1 flex-col justify-center gap-2">
          <div
            className="text-[30px] font-bold leading-none tabular-nums text-[var(--color-text-2)]"
            data-mongodb-conn-reading=""
          >
            —
          </div>
          <p className="m-0 text-[13px] leading-5 text-[var(--color-text-3)]">本窗口暂无数据</p>
        </div>
      ) : (
        <div className="flex flex-1 flex-col justify-center">
          <div
            className="text-[30px] font-bold leading-none tabular-nums text-[var(--color-text-1)]"
            data-mongodb-conn-reading=""
          >
            {formatMongoReading(current, 'counts')}
          </div>
          {openText || capText ? (
            <div className="mt-3 flex w-full flex-col gap-0.5" data-mongodb-conn-note="">
              {openText ? (
                <p className="m-0 text-[13px] leading-5 tabular-nums text-[var(--color-text-3)]" data-mongodb-conn-open="">
                  打开 {openText}
                </p>
              ) : null}
              {capText ? (
                <p className="m-0 text-[13px] leading-5 tabular-nums text-[var(--color-text-3)]" data-mongodb-conn-cap="">
                  上限 {capText}
                </p>
              ) : null}
            </div>
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
            <CurrentConnectionsCard metricMap={metricMap} pending={pendingMetricNames} />
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
              activeQueue
            />
          </div>
        </div>
      </ProSection>
      <ProSection title="网络">
        <div className="flex min-w-0 flex-col gap-3" data-mongodb-zone="network">
          {NETWORK_CHARTS.map((chart) => (
            <div key={chart.anchor} className={host.mongoChartCell}>
              <MongoTrend
                anchor={chart.anchor}
                title={chart.title}
                body={chart.body}
                series={chart.series}
                metricMap={metricMap}
                pending={pendingMetricNames}
                compactEmpty
              />
            </div>
          ))}
        </div>
      </ProSection>
    </div>
  );
}
