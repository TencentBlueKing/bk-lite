import { hasRenderableWidgetData } from '@/app/ops-analysis/renderContract';
import {
  isEmptyTopologyMapPayload,
  parseTopologyMapPayload,
} from '@/app/ops-analysis/utils/topologyMapData';

export const validateTopologyMapWidgetData = (
  data: unknown,
  errorMessage: string,
): { isValid: boolean; message?: string } => {
  const parsed = parseTopologyMapPayload(data);
  if (!('error' in parsed)) return { isValid: true };
  return { isValid: false, message: errorMessage };
};

export const hasRenderableChartData = (
  chartType: string | undefined,
  data: unknown,
) => {
  if (chartType !== 'topologyMap') return hasRenderableWidgetData(data);
  const parsed = parseTopologyMapPayload(data);
  return parsed.ok && !isEmptyTopologyMapPayload(parsed.data);
};
