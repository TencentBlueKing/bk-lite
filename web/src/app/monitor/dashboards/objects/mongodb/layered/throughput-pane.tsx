'use client';

import { ProSection } from '../../host/layered/pro-chrome';
import { EVENT_CHARTS, THROUGHPUT_DOCUMENT_CHARTS } from './chart-specs';
import { MongoChartGrid } from './chart-grid';
import type { MongoMetricMap } from './series';

export default function ThroughputPane({
  metricMap,
  pendingMetricNames
}: {
  metricMap: MongoMetricMap;
  pendingMetricNames: ReadonlySet<string>;
}) {
  return (
    <div data-mongodb-pane="throughput" className="contents">
      <ProSection title="吞吐与文档">
        <MongoChartGrid
          charts={THROUGHPUT_DOCUMENT_CHARTS}
          zone="throughput"
          metricMap={metricMap}
          pendingMetricNames={pendingMetricNames}
        />
      </ProSection>
      <ProSection title="事件">
        <MongoChartGrid
          charts={EVENT_CHARTS}
          zone="events"
          metricMap={metricMap}
          pendingMetricNames={pendingMetricNames}
        />
      </ProSection>
    </div>
  );
}
