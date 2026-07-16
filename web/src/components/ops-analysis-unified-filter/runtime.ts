import type {
  DatasourceItem,
  FilterBindings,
  FilterValue,
  ParamItem,
  UnifiedFilterDefinition,
} from '@/components/ops-analysis-widgets';

export type BindableParamType = 'string' | 'timeRange';
export type UnifiedFilterInputMode =
  | 'input'
  | 'select'
  | 'radio'
  | 'organization';

export interface UnifiedFilterLayoutItemLike {
  valueConfig?: {
    dataSource?: string | number;
  };
}

const UNIFIED_FILTER_INPUT_MODES: UnifiedFilterInputMode[] = [
  'input',
  'select',
  'radio',
  'organization',
];

const OPTION_INPUT_MODES: UnifiedFilterInputMode[] = ['select', 'radio'];

export const normalizeUnifiedFilterInputMode = (
  inputMode?: string,
): UnifiedFilterInputMode =>
  UNIFIED_FILTER_INPUT_MODES.includes(inputMode as UnifiedFilterInputMode)
    ? (inputMode as UnifiedFilterInputMode)
    : 'input';

export const isOptionInputMode = (inputMode?: string): boolean =>
  OPTION_INPUT_MODES.includes(normalizeUnifiedFilterInputMode(inputMode));

export const sanitizeUnifiedFilterDefinition = <
  T extends UnifiedFilterDefinition,
>(
    definition: T,
  ): T => {
  if (definition.type === 'timeRange') {
    const next = { ...definition };
    delete next.inputMode;
    delete next.options;
    return next;
  }

  const inputMode = normalizeUnifiedFilterInputMode(definition.inputMode);
  if (!isOptionInputMode(inputMode)) {
    const next = { ...definition };
    delete next.options;
    return {
      ...next,
      inputMode,
    };
  }

  const options = Array.isArray(definition.options) ? definition.options : [];
  const optionValues = options.map((item) => item.value);
  const defaultValue =
    typeof definition.defaultValue === 'string' &&
    optionValues.includes(definition.defaultValue)
      ? definition.defaultValue
      : null;

  return {
    ...definition,
    inputMode,
    options,
    defaultValue,
  };
};

export const getFilterDefinitionId = (
  key: string,
  type: BindableParamType,
): string => `${key}__${type}`;

export const getBindableFilterParams = (
  params?: ParamItem[],
): Array<ParamItem & { type: BindableParamType }> =>
  (Array.isArray(params) ? params : []).filter(
    (param): param is ParamItem & { type: BindableParamType } =>
      param.filterType === 'filter' &&
      (param.type === 'string' || param.type === 'timeRange'),
  );

export const buildDefaultFilterBindings = (
  params: ParamItem[] | undefined,
  definitions: UnifiedFilterDefinition[],
  existingBindings?: FilterBindings,
): FilterBindings | undefined => {
  const bindableParams = getBindableFilterParams(params);
  if (!bindableParams.length || !definitions.length) {
    return existingBindings;
  }

  const autoBindings = definitions.reduce<FilterBindings>((acc, definition) => {
    const matched = bindableParams.some(
      (param) => param.name === definition.key && param.type === definition.type,
    );
    if (matched) {
      acc[definition.id] = true;
    }
    return acc;
  }, {});

  if (!Object.keys(autoBindings).length) {
    return existingBindings;
  }

  return {
    ...autoBindings,
    ...(existingBindings || {}),
  };
};

export const scanUnifiedFilterParams = (
  layoutItems: UnifiedFilterLayoutItemLike[],
  dataSources: DatasourceItem[],
) => {
  const paramMap = new Map<
    string,
    {
      key: string;
      type: BindableParamType;
      componentCount: number;
      sampleAlias: string;
      sampleDefaultValue: FilterValue;
    }
  >();

  const usedDataSourceIds = new Set<number>();
  layoutItems.forEach((item) => {
    const dsId = item.valueConfig?.dataSource;
    if (dsId) {
      usedDataSourceIds.add(typeof dsId === 'string' ? parseInt(dsId, 10) : dsId);
    }
  });

  dataSources.forEach((ds) => {
    if (!usedDataSourceIds.has(ds.id)) return;

    getBindableFilterParams(ds.params).forEach((param) => {
      const compositeKey = `${param.name}__${param.type}`;
      const existing = paramMap.get(compositeKey);

      if (existing) {
        existing.componentCount += 1;
      } else {
        paramMap.set(compositeKey, {
          key: param.name,
          type: param.type,
          componentCount: 1,
          sampleAlias: param.alias_name || param.name,
          sampleDefaultValue: (param.value as FilterValue) ?? null,
        });
      }
    });
  });

  return Array.from(paramMap.values());
};
