import type { ComponentType } from 'react';
import ComPie from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comPie';
import ComLine from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comLine';
import ComBar from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comBar';
import ComTable from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comTable';
import ComSingle from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comSingle';
import ComTopN from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comTopN';
import ComGauge from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comGauge';
import ComMessage from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comMessage';

export const widgetRegistry: Record<string, ComponentType<any>> = {
  line: ComLine,
  pie: ComPie,
  bar: ComBar,
  table: ComTable,
  single: ComSingle,
  topN: ComTopN,
  gauge: ComGauge,
  message: ComMessage,
};

export const getWidgetComponent = (chartType?: string) => {
  if (!chartType) {
    return null;
  }

  return widgetRegistry[chartType] || null;
};
