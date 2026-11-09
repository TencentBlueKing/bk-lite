'use client';

import host from '../../host/layered/layered.module.scss';
import type { MongoChartSpec } from './chart-specs';
import type { MongoMetricMap } from './series';
import { MongoTrend } from './trend';

export function MongoChartGrid({
  charts,
  zone,
  metricMap,
  pendingMetricNames,
  spanRow = false
}: {
  charts: readonly MongoChartSpec[];
  zone: string;
  metricMap: MongoMetricMap;
  pendingMetricNames: ReadonlySet<string>;
  /** 单卡铺满一行，避免半行留白。高度仍跟折线卡，不跟着拉长。 */
  spanRow?: boolean;
}) {
  return (
    <div className={host.chartGrid2} data-mongodb-zone={zone}>
      {charts.map((chart) => {
        const trend = (
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
        );
        if (!spanRow) return <div key={chart.anchor} className="min-w-0 h-full">{trend}</div>;
        return (
          <div key={chart.anchor} className="min-w-0 h-full min-[1101px]:col-span-2">
            {trend}
          </div>
        );
      })}
    </div>
  );
}
