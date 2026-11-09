'use client';

import { ProSection } from '../../host/layered/pro-chrome';
import { CONNECTION_CHARTS } from './chart-specs';
import { MongoChartGrid } from './chart-grid';
import type { MongoMetricMap } from './series';

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
        <MongoChartGrid
          charts={CONNECTION_CHARTS}
          zone="connections"
          metricMap={metricMap}
          pendingMetricNames={pendingMetricNames}
        />
      </ProSection>
    </div>
  );
}
