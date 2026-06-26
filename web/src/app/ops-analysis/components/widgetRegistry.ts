import type { ComponentType } from 'react';
import ComPie from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comPie';
import ComLine from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comLine';
import ComBar from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comBar';
import ComTable from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comTable';
import ComSingle from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comSingle';
import ComTopN from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comTopN';
import ComGauge from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comGauge';
import ComBarGauge from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comBarGauge';
import ComStateTimeline from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comStateTimeline';
import ComText from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comText';
import EventTable from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/eventTable/eventTable';
import NetworkStatusTopology from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology';

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
