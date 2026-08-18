import { validateRoom3DData } from '@/app/ops-analysis/components/widgets/room3D/room3DData';
import { hasRenderableWidgetData } from '@/app/ops-analysis/renderContract';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import {
  extractComparableValue,
  toComparableNumber,
} from '@/app/ops-analysis/utils/compareQuery';
import { parseTableLikeData } from '@/app/ops-analysis/utils/tableLikeData';
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

/**
 * Whether this payload will eventually call onReady(true).
 * handleRendererReady keeps status at loading when the renderer reports empty
 * but this is true — that wait is only valid for async layout (topologyMap /
 * room3D with racks). Sync empty UIs must return false here or reports hang.
 */
export const hasRenderableChartData = (
  chartType: string | undefined,
  data: unknown,
  config?: { selectedFields?: string[] },
) => {
  if (chartType === 'topologyMap') {
    const parsed = parseTopologyMapPayload(data);
    return parsed.ok && !isEmptyTopologyMapPayload(parsed.data);
  }
  if (chartType === 'pie') {
    return ChartDataTransformer.transformToPieData(data).some(
      (item) => Number.isFinite(item.value) && item.value > 0,
    );
  }
  if (chartType === 'single') {
    return extractComparableValue(data, config?.selectedFields?.[0]) !== null;
  }
  if (chartType === 'gauge') {
    return (
      toComparableNumber(
        extractComparableValue(data, config?.selectedFields?.[0]),
      ) !== null
    );
  }
  if (chartType === 'line' || chartType === 'bar') {
    return (
      ChartDataTransformer.transformToLineBarData(data).categories.length > 0
    );
  }
  if (chartType === 'table' || chartType === 'eventTable') {
    return parseTableLikeData(data, { current: 1, pageSize: 20 }).rows.length > 0;
  }
  if (chartType === 'room3D') {
    const parsed = validateRoom3DData(data);
    return (
      parsed.ok &&
      (parsed.data.racks.length > 0 || Boolean(parsed.data.notice))
    );
  }
  return hasRenderableWidgetData(data);
};
