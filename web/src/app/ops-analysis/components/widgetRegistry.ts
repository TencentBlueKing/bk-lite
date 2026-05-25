import type { ComponentType } from 'react';
import ComPie from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comPie';
import ComLine from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comLine';
import ComBar from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comBar';
import ComTable from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comTable';
import ComSingle from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comSingle';
import ComTopN from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/comTopN';

export const widgetRegistry: Record<string, ComponentType<any>> = {
  line: ComLine,
  pie: ComPie,
  bar: ComBar,
  table: ComTable,
  single: ComSingle,
  topN: ComTopN,
};

export const getWidgetComponent = (chartType?: string) => {
  if (!chartType) {
    return null;
  }

  return widgetRegistry[chartType] || null;
};
