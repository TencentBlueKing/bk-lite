import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
import {
  filterChartTypesForSurface,
  type OpsAnalysisWidgetSurface,
} from '@/app/ops-analysis/utils/chartTypeSurface';
import type { DisplayColumnRow } from './columnProbing';

interface BuildDisplayColumnFieldOptionsInput {
  availableFields?: ResponseFieldDefinition[];
  displayColumns?: DisplayColumnRow[];
  detectedColumns?: Array<Pick<DisplayColumnRow, 'key' | 'title'>>;
}

export interface TableFieldOption {
  label: string;
  value: string;
}

const formatFieldOptionLabel = (key: string, title?: string) => {
  const normalizedKey = (key || '').trim();
  const normalizedTitle = (title || '').trim();

  if (!normalizedKey) {
    return '';
  }

  if (!normalizedTitle || normalizedTitle === normalizedKey) {
    return normalizedKey;
  }

  return `${normalizedKey} (${normalizedTitle})`;
};

export const buildDisplayColumnFieldOptions = ({
  availableFields = [],
  displayColumns = [],
  detectedColumns = [],
}: BuildDisplayColumnFieldOptionsInput): TableFieldOption[] => {
  const optionMap = new Map<string, TableFieldOption>();

  const appendOption = (key: string, title?: string) => {
    const normalizedKey = (key || '').trim();
    if (!normalizedKey || optionMap.has(normalizedKey)) {
      const current = optionMap.get(normalizedKey);
      const nextLabel = formatFieldOptionLabel(normalizedKey, title);
      if (current && current.label === normalizedKey && nextLabel !== normalizedKey) {
        optionMap.set(normalizedKey, {
          ...current,
          label: nextLabel,
        });
      }
      return;
    }

    optionMap.set(normalizedKey, {
      label: formatFieldOptionLabel(normalizedKey, title),
      value: normalizedKey,
    });
  };

  availableFields.forEach((field) => {
    appendOption(field.key, field.title);
  });

  detectedColumns.forEach((column) => {
    appendOption(column.key, column.title);
  });

  displayColumns.forEach((column) => {
    appendOption(column.key, column.title);
  });

  return Array.from(optionMap.values());
};

export const shouldShowTableFilterFields = (chartType: string) =>
  chartType === 'table';

interface ResolveDatasourceChartTypesInput<ChartTypeDefinition extends { value: string }> {
  chartTypes?: string[];
  chartTypeDefinitions: ChartTypeDefinition[];
  surface?: OpsAnalysisWidgetSurface;
}

export const resolveDatasourceChartTypes = <
  ChartTypeDefinition extends { value: string },
>({
    chartTypes = [],
    chartTypeDefinitions,
    surface = 'dashboard',
  }: ResolveDatasourceChartTypesInput<ChartTypeDefinition>) => {
  const surfaceChartTypes = filterChartTypesForSurface(chartTypes, surface);
  const uniqueTypes = surfaceChartTypes.filter(
    (type, index, list) => list.indexOf(type) === index,
  );

  return uniqueTypes
    .map((type) =>
      chartTypeDefinitions.find((chartType) => chartType.value === type),
    )
    .filter((item): item is ChartTypeDefinition => Boolean(item));
};
