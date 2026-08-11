import type { TableColumnConfigItem } from '@/app/ops-analysis/types/dashBoard';
import { applyValueMapping } from '@/app/ops-analysis/utils/valueMapping';
import { getColorByThreshold } from '@/app/ops-analysis/utils/thresholdUtils';

export type TableCellPresentation =
  | {
      mode: 'text';
      displayText: string;
      color?: string;
    }
  | {
      mode: 'colorBackground';
      color: string;
      tooltipText: string;
    };

type TableCellStyleConfig = Pick<
  TableColumnConfigItem,
  'valueMappings' | 'cellThresholdColors' | 'cellType'
>;

const toDisplayText = (raw: unknown, mappedText?: string): string => {
  if (mappedText !== undefined) return mappedText;
  if (raw === null || raw === undefined) return '--';
  const text = String(raw);
  return text.trim() ? text : '--';
};

export const resolveTableCellPresentation = (
  raw: unknown,
  config: TableCellStyleConfig = {},
): TableCellPresentation => {
  const mapping = applyValueMapping(raw, config.valueMappings);
  const displayText = toDisplayText(raw, mapping?.text);
  const numericValue =
    typeof raw === 'number' ? raw : parseFloat(String(raw ?? ''));
  const thresholdColor =
    config.cellThresholdColors?.length && !Number.isNaN(numericValue)
      ? getColorByThreshold(numericValue, config.cellThresholdColors, '')
      : '';
  const cellColor = mapping?.color || thresholdColor || undefined;

  if (config.cellType === 'colorBackground' && cellColor) {
    return {
      mode: 'colorBackground',
      color: cellColor,
      tooltipText: displayText,
    };
  }

  return {
    mode: 'text',
    displayText,
    ...(cellColor ? { color: cellColor } : {}),
  };
};
