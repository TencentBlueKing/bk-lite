import type { ComponentType } from 'react';
import ComPie from '@/app/ops-analysis/components/widgets/comPie';
import ComLine from '@/app/ops-analysis/components/widgets/comLine';
import ComBar from '@/app/ops-analysis/components/widgets/comBar';
import ComTable from '@/app/ops-analysis/components/widgets/comTable';
import ComSingle from '@/app/ops-analysis/components/widgets/comSingle';
import ComTopN from '@/app/ops-analysis/components/widgets/comTopN';
import ComGauge from '@/app/ops-analysis/components/widgets/comGauge';
import ComBarGauge from '@/app/ops-analysis/components/widgets/comBarGauge';
import ComStateTimeline from '@/app/ops-analysis/components/widgets/comStateTimeline';
import ComText from '@/app/ops-analysis/components/widgets/comText';
import EventTable from '@/app/ops-analysis/components/widgets/eventTable/eventTable';
import NetworkStatusTopology from '@/app/ops-analysis/components/widgets/networkStatusTopology';

export const widgetRegistry: Record<string, ComponentType<any>> = {
  line: ComLine,
  pie: ComPie,
  bar: ComBar,
  table: ComTable,
  single: ComSingle,
  topN: ComTopN,
  gauge: ComGauge,
  barGauge: ComBarGauge,
  stateTimeline: ComStateTimeline,
  text: ComText,
  eventTable: EventTable,
  networkStatusTopology: NetworkStatusTopology,
};

export const getWidgetComponent = (chartType?: string) => {
  if (!chartType) {
    return null;
  }

  return widgetRegistry[chartType] || null;
};
