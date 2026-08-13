import type { ComponentType } from 'react';
import ComPie from '@/app/ops-analysis/components/widgets/comPie';
import ComLine from '@/app/ops-analysis/components/widgets/comLine';
import ComBar from '@/app/ops-analysis/components/widgets/comBar';
import ComTable from '@/app/ops-analysis/components/widgets/comTable';
import ComSingle from '@/app/ops-analysis/components/widgets/comSingle';
import ComTopN from '@/app/ops-analysis/components/widgets/comTopN';
import ComGauge from '@/app/ops-analysis/components/widgets/comGauge';
import EventTable from '@/app/ops-analysis/components/widgets/eventTable/eventTable';
import NetworkStatusTopology from '@/app/ops-analysis/components/widgets/networkStatusTopology';
import Room3D from '@/app/ops-analysis/components/widgets/room3D';
import ComMultiValue from '@/app/ops-analysis/components/widgets/comMultiValue';
import ComEventTimeline from '@/app/ops-analysis/components/widgets/comEventTimeline';
import ComCardList from '@/app/ops-analysis/components/widgets/comCardList';
import ComRadar from '@/app/ops-analysis/components/widgets/comRadar';
import OpsAnalysisTextPanel from '@/app/ops-analysis/components/ops-analysis-widgets/text-panel';
import TopologyMap from '@/app/ops-analysis/components/widgets/topologyMap';

export const widgetRegistry: Record<string, ComponentType<any>> = {
  line: ComLine,
  pie: ComPie,
  bar: ComBar,
  table: ComTable,
  single: ComSingle,
  topN: ComTopN,
  gauge: ComGauge,
  eventTable: EventTable,
  eventTimeline: ComEventTimeline,
  cardList: ComCardList,
  radar: ComRadar,
  room3D: Room3D,
  networkStatusTopology: NetworkStatusTopology,
  multiValue: ComMultiValue,
  text: OpsAnalysisTextPanel,
  topologyMap: TopologyMap,
};

export const getWidgetComponent = (chartType?: string) => {
  if (!chartType) {
    return null;
  }

  return widgetRegistry[chartType] || null;
};
