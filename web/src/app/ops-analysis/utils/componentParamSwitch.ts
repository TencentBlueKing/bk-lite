import type { InputOption, ParamItem } from '@/app/ops-analysis/types/dataSource';

type SwitchableInputConfig = NonNullable<ParamItem['inputConfig']> & {
  componentSwitch?: boolean;
};

export const getTypedValueKey = (value: string | number): string =>
  `${typeof value}:${String(value)}`;

export const isComponentSwitchCandidate = (param: ParamItem): boolean => {
  const inputConfig = param.inputConfig as SwitchableInputConfig | undefined;
  return param.filterType === 'params'
    && param.type === 'string'
    && (inputConfig?.control === 'select' || inputConfig?.control === 'radio')
    && inputConfig.componentSwitch === true;
};

export const getComponentSwitchCandidates = (params?: ParamItem[]): ParamItem[] =>
  (params || []).filter(isComponentSwitchCandidate);

export const findComponentSwitchParams = getComponentSwitchCandidates;

export type ComponentSwitchValidationError = 'multipleComponentSwitchParams';

export interface ComponentSwitchValidation {
  valid: boolean;
  params: ParamItem[];
}

export const validateComponentSwitchDetails = (
  params?: ParamItem[],
): ComponentSwitchValidation => {
  const switchParams = findComponentSwitchParams(params);
  return { valid: switchParams.length <= 1, params: switchParams };
};

export const validateComponentSwitchParams = (
  params?: ParamItem[],
): ComponentSwitchValidationError | null =>
  findComponentSwitchParams(params).length > 1 ? 'multipleComponentSwitchParams' : null;

export const validateComponentParamSwitch = validateComponentSwitchParams;

export const reconcileComponentSwitchValue = (
  value: ParamItem['value'] | undefined,
  options?: InputOption[],
): ParamItem['value'] | undefined => {
  if (!options?.length) return value;
  const currentKey = typeof value === 'string' || typeof value === 'number'
    ? getTypedValueKey(value)
    : null;
  return currentKey && options.some((option) => getTypedValueKey(option.value) === currentKey)
    ? value
    : options[0].value;
};

export const reconcileComponentParamValue = reconcileComponentSwitchValue;

export const reconcileComponentSwitchResult = (
  value: ParamItem['value'] | undefined,
  options?: InputOption[],
): { value: ParamItem['value'] | undefined; changed: boolean } => {
  const reconciled = reconcileComponentSwitchValue(value, options);
  return { value: reconciled, changed: reconciled !== value };
};

export const clearComponentParamSwitch = (param: ParamItem): ParamItem => {
  const inputConfig = param.inputConfig as SwitchableInputConfig | undefined;
  if (!inputConfig || !('componentSwitch' in inputConfig)) return param;
  if (inputConfig.control === 'input') {
    const nextInputConfig = { ...inputConfig } as Record<string, unknown>;
    delete nextInputConfig.componentSwitch;
    return { ...param, inputConfig: nextInputConfig as ParamItem['inputConfig'] };
  }
  return {
    ...param,
    inputConfig: {
      control: inputConfig.control,
      optionsSource: inputConfig.optionsSource,
    },
  };
};

export const clearComponentSwitch = (params?: ParamItem[]): ParamItem[] =>
  (params || []).map(clearComponentParamSwitch);

export const buildComponentSwitchRuntimeParams = (
  param: ParamItem | undefined,
  value: unknown,
  options?: InputOption[],
): Record<string, string | number> => {
  if (!param || !isComponentSwitchCandidate(param) || !param.name.trim()) return {};
  if (typeof value !== 'string' && typeof value !== 'number') return {};
  if (!options?.some((option) => getTypedValueKey(option.value) === getTypedValueKey(value))) {
    return {};
  }
  return { [param.name]: value };
};

export const resolveComponentSwitchRuntime = (
  chartType: string | undefined,
  param: ParamItem | undefined,
  options: InputOption[],
  currentValue: ParamItem['value'] | undefined,
): { value: string | number | undefined; params: Record<string, string | number> } => {
  if (chartType !== 'topN' || !param || !isComponentSwitchCandidate(param) || !options.length) {
    return { value: undefined, params: {} };
  }
  const reconciled = reconcileComponentSwitchResult(currentValue, options).value;
  if (typeof reconciled !== 'string' && typeof reconciled !== 'number') {
    return { value: undefined, params: {} };
  }
  const params = buildComponentSwitchRuntimeParams(param, reconciled, options);
  return Object.keys(params).length ? { value: reconciled, params } : { value: undefined, params: {} };
};
