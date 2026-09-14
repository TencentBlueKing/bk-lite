import type {
  DynamicOptionsSource,
  InputControlConfig,
  InputOption,
} from '@/app/ops-analysis/types/dataSource';

export const ORGANIZATION_PARAM_RUNTIME_KEY = 'organization_param';

interface LegacyOptionsEntity {
  inputConfig?: InputControlConfig | { control?: string; multiple?: boolean };
  options?: InputOption[];
  inputMode?: string;
}

interface SourceLike {
  id: number;
  name?: string;
  rest_api?: string;
}

export const isOptionInputControl = (
  config?: InputControlConfig,
): config is Extract<InputControlConfig, { control: 'select' | 'radio' }> =>
  config?.control === 'select' || config?.control === 'radio';

export const normalizeInputConfig = (
  entity?: LegacyOptionsEntity | null,
): InputControlConfig | undefined => {
  if (!entity) return undefined;
  if (entity.inputConfig) {
    if (entity.inputConfig.control === 'organization') {
      return { control: 'organization' };
    }
    return entity.inputConfig as InputControlConfig;
  }
  if (entity.inputMode === 'organization') {
    return { control: 'organization' };
  }
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

export const isOrganizationControl = (
  entity?: LegacyOptionsEntity | null,
): boolean => normalizeInputConfig(entity)?.control === 'organization';

export const toSingleOrganizationValue = (value: unknown): number | undefined => {
  if (typeof value !== 'string' && typeof value !== 'number') return undefined;
  const normalized = Number(value);
  return Number.isNaN(normalized) ? undefined : normalized;
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
  if (source.sourceRef?.type === 'rest_api') {
    const ref = source.sourceRef.value;
    const byKey = dataSources.find(
      (item) =>
        typeof item.name === 'string' &&
        item.name.length > 0 &&
        `${item.name}::${item.rest_api || ''}` === ref,
    );
    if (byKey) return byKey.id;
    return dataSources.find((item) => item.rest_api === ref)?.id;
  }
  return typeof source.sourceId === 'number' ? source.sourceId : undefined;
};
