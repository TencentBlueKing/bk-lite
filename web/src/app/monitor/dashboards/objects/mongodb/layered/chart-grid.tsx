'use client';

import host from '../../host/layered/layered.module.scss';
import type { MongoChartSpec } from './chart-specs';
import type { MongoMetricMap } from './series';
import { MongoTrend } from './trend';

export function MongoChartGrid({
  charts,
  zone,
  metricMap,
  pendingMetricNames
}: {
  charts: readonly MongoChartSpec[];
  zone: string;
  metricMap: MongoMetricMap;
  pendingMetricNames: ReadonlySet<string>;
}) {
  return (
    <div className={host.chartGrid2} data-mongodb-zone={zone} data-mongodb-span="cell">
      {charts.map((chart) => (
        <div key={chart.anchor} className={host.mongoChartCell}>
          <MongoTrend
            anchor={chart.anchor}
            title={chart.title}
            body={chart.body}
            series={chart.series}
            metricMap={metricMap}
            pending={pendingMetricNames}
            counts={chart.counts}
            emptyText={chart.emptyText}
          />
        </div>
      ))}
    </div>
  );
}
