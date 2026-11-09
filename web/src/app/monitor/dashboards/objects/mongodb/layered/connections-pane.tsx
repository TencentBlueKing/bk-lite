'use client';

import { ProDashLoading, ProSectionTitle, proChromeClass } from '../../host/layered/pro-chrome';
import { CONNECTION_CHARTS } from './chart-specs';
import { MongoChartGrid } from './chart-grid';
import { MongoHint } from './hint';
import { formatMongoReading, mongoLatest, type MongoMetricMap } from './series';

const AVAILABLE_METRIC = 'mongodb_connections_available';
const AVAILABLE_BODY = '当前还能再接纳的连接数。和当前、打开连接不共用一条轴，避免大数把并发变化压扁。';

function AvailableConnectionsCard({
  metricMap,
  pending
}: {
  metricMap: MongoMetricMap;
  pending: ReadonlySet<string>;
}) {
  const latest = mongoLatest(metricMap, AVAILABLE_METRIC);
  const waiting = latest == null && pending.has(AVAILABLE_METRIC);
  return (
    <div
      className={`${proChromeClass.kpiCard}${waiting ? ` ${proChromeClass.kpiCardLoading}` : ''}`}
      data-mongodb-kpi="connections-available"
      data-mongodb-connections-available={waiting ? 'loading' : latest == null ? 'missing' : String(latest)}
    >
      {waiting ? <ProDashLoading size="small" /> : (
        <>
          <div className={`${proChromeClass.kpiLabel} inline-flex max-w-full items-center gap-1 !overflow-visible`}>
            <span className="min-w-0 truncate">尚可接纳连接</span>
            <MongoHint kind="mongo-kpi-connections-available" title="尚可接纳连接" body={AVAILABLE_BODY} />
          </div>
          <div className={proChromeClass.kpiValue}>
            {formatMongoReading(latest, 'counts')}
          </div>
        </>
      )}
    </div>
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
      <section className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <ProSectionTitle>连接</ProSectionTitle>
          <div className="w-[11.5rem] max-w-full shrink-0">
            <AvailableConnectionsCard metricMap={metricMap} pending={pendingMetricNames} />
          </div>
        </div>
        <MongoChartGrid
          charts={CONNECTION_CHARTS}
          zone="connections"
          metricMap={metricMap}
          pendingMetricNames={pendingMetricNames}
        />
      </section>
    </div>
  );
}
