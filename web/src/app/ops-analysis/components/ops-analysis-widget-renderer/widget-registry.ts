import type { ComponentType } from 'react';
import {
  OpsAnalysisBar,
  OpsAnalysisBarGauge,
  OpsAnalysisEventTable,
  OpsAnalysisEventTimeline,
  OpsAnalysisGauge,
  OpsAnalysisLine,
  OpsAnalysisPie,
  OpsAnalysisRadar,
  OpsAnalysisSingle,
  OpsAnalysisStateTimeline,
  OpsAnalysisTable,
  OpsAnalysisTextPanel,
  OpsAnalysisTopN,
} from '@/app/ops-analysis/components/ops-analysis-widgets';

export const opsAnalysisWidgetRegistry: Record<string, ComponentType<any>> = {
  line: OpsAnalysisLine,
  pie: OpsAnalysisPie,
  bar: OpsAnalysisBar,
  table: OpsAnalysisTable,
  single: OpsAnalysisSingle,
  topN: OpsAnalysisTopN,
  gauge: OpsAnalysisGauge,
  barGauge: OpsAnalysisBarGauge,
  stateTimeline: OpsAnalysisStateTimeline,
  text: OpsAnalysisTextPanel,
  eventTable: OpsAnalysisEventTable,
  eventTimeline: OpsAnalysisEventTimeline,
  radar: OpsAnalysisRadar,
};

export const getOpsAnalysisWidgetComponent = (chartType?: string) => {
  if (!chartType) {
    return null;
  }

  return opsAnalysisWidgetRegistry[chartType] || null;
};
