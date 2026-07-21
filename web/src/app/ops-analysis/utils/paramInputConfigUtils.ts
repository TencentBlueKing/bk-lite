import type {
  DynamicOptionsSource,
  InputControlConfig,
  InputOption,
} from '@/app/ops-analysis/types/dataSource';

type LegacyOptionsEntity = {
  inputConfig?: InputControlConfig;
  options?: InputOption[];
};

type SourceLike = {
  id: number;
  rest_api?: string;
};

export const normalizeInputConfig = (
  entity?: LegacyOptionsEntity | null,
): InputControlConfig | undefined => {
  if (!entity) return undefined;
  if (entity.inputConfig) return entity.inputConfig;
  if (Array.isArray(entity.options) && entity.options.length > 0) {
    return {
      control: 'select',
      optionsSource: {
        type: 'static',
        staticItems: entity.options,
      },
    };
  }
  return undefined;
};

export const extractDataSourceItems = (
  response: unknown,
): Record<string, unknown>[] => {
  if (Array.isArray(response)) return response as Record<string, unknown>[];
  if (!response || typeof response !== 'object') return [];

  const record = response as Record<string, unknown>;
  if (Array.isArray(record.items)) return record.items as Record<string, unknown>[];

  const data = record.data;
  if (data && typeof data === 'object' && Array.isArray((data as Record<string, unknown>).items)) {
    return (data as Record<string, unknown>).items as Record<string, unknown>[];
  }

  return [];
};

export const mapDynamicItems = (
  items: Record<string, unknown>[],
  valueField: string,
  labelField: string,
): InputOption[] => {
  return items
    .filter((item): item is Record<string, unknown> => {
      return item !== null && typeof item === 'object' && !Array.isArray(item);
    })
    .map((item) => {
      const value = item[valueField];
      if (value === undefined || value === null) return null;
      if (typeof value !== 'string' && typeof value !== 'number') return null;
      return {
        value,
        label: String(item[labelField] ?? ''),
      };
    })
    .filter((item): item is InputOption => item !== null);
};

export const resolveDynamicSourceId = (
  source: DynamicOptionsSource,
  dataSources: SourceLike[],
): number | undefined => {
  if (typeof source.sourceId === 'number') return source.sourceId;
  if (source.sourceRef?.type !== 'rest_api') return undefined;
  return dataSources.find((item) => item.rest_api === source.sourceRef?.value)?.id;
};
