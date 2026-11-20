import type { InputOption, ParamItem } from '@/app/ops-analysis/types/dataSource';
import { isSelfFetchSceneWidget } from '@/app/ops-analysis/types/sceneWidgetCapability';
import { isOptionInputControl } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import {
  isMultipleSelectInputConfig,
  type StringParamMigrationWarning,
} from '@/app/ops-analysis/utils/stringParamMultipleMigrate';

type SwitchableInputConfig = NonNullable<ParamItem['inputConfig']> & {
  componentSwitch?: boolean;
};

const NO_DATA_REQUEST_CHART_TYPES = new Set(['text']);

export type ComponentSwitchRuntimeValue = string | number | Array<string | number>;

export const supportsComponentSwitch = (chartType?: string): boolean =>
  Boolean(
    chartType
    && !NO_DATA_REQUEST_CHART_TYPES.has(chartType)
    && !isSelfFetchSceneWidget(chartType),
  );

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
  if (!options) return value;
  if (typeof value !== 'string' && typeof value !== 'number') return null;
  return options.some((option) => getTypedValueKey(option.value) === getTypedValueKey(value))
    ? value
    : null;
};

/**
 * 通用查询参数与选项对齐：多选数组保留仍存在于选项中的值；
 * 标量与组件切换一致：不在选项里则清空，不落到 options[0]。
 * `options` 未传入表示还在加载，保留现值；空数组表示上游为空或已经没有候选项，清空失效值。
 */
export const sameParamValue = (
  left: ParamItem['value'] | undefined,
  right: ParamItem['value'] | undefined,
): boolean => {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length
      && left.every((item, index) => Object.is(item, right[index]));
  }
  return false;
};

export const reconcileComponentParamValue = (
  value: ParamItem['value'] | undefined,
  options?: InputOption[],
): ParamItem['value'] | undefined => {
  if (options == null) return value;
  if (Array.isArray(value)) {
    const optionKeys = new Set(
      options.map((option) => getTypedValueKey(option.value)),
    );
    return value.filter(
      (item): item is string | number =>
        (typeof item === 'string' || typeof item === 'number')
        && optionKeys.has(getTypedValueKey(item)),
    );
  }
  return reconcileComponentSwitchValue(value, options);
};

export const reconcileComponentSwitchResult = (
  value: ParamItem['value'] | undefined,
  options?: InputOption[],
): { value: ParamItem['value'] | undefined; changed: boolean } => {
  const reconciled = reconcileComponentSwitchValue(value, options);
  return { value: reconciled, changed: reconciled !== value };
};

const isSwitchScalar = (value: unknown): value is string | number =>
  typeof value === 'string' || typeof value === 'number';

/** 组件内切换的当前选择。多选必须整组都在选项里，否则整组清空。 */
export const reconcileComponentSwitchSelection = (
  value: ParamItem['value'] | undefined,
  options: InputOption[] | undefined,
  multiple: boolean,
): ParamItem['value'] | null | undefined => {
  if (options == null) return value;
  if (!multiple) return reconcileComponentSwitchValue(value, options);
  const items = Array.isArray(value)
    ? value
    : (isSwitchScalar(value) ? [value] : []);
  const scalars = items.filter(isSwitchScalar);
  if (scalars.length === 0 || scalars.length !== items.length) return null;
  const optionKeys = new Set(options.map((option) => getTypedValueKey(option.value)));
  if (!scalars.every((item) => optionKeys.has(getTypedValueKey(item)))) return null;
  return scalars;
};

export const clearComponentParamSwitch = (param: ParamItem): ParamItem => {
  const inputConfig = param.inputConfig as SwitchableInputConfig | undefined;
  if (!inputConfig || !('componentSwitch' in inputConfig)) return param;
  if (!isOptionInputControl(inputConfig)) {
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
): Record<string, ComponentSwitchRuntimeValue> => {
  if (!param || !isComponentSwitchCandidate(param) || !param.name.trim() || !options?.length) return {};
  const multiple = isMultipleSelectInputConfig(param.inputConfig);
  const reconciled = reconcileComponentSwitchSelection(
    value as ParamItem['value'],
    options,
    multiple,
  );
  if (multiple) {
    if (!Array.isArray(reconciled) || reconciled.length === 0) return {};
    return { [param.name]: reconciled };
  }
  if (!isSwitchScalar(reconciled)) return {};
  return { [param.name]: reconciled };
};

export const resolveComponentSwitchRuntime = (
  chartType: string | undefined,
  param: ParamItem | undefined,
  options: InputOption[],
  currentValue: ParamItem['value'] | undefined,
): {
  value: ComponentSwitchRuntimeValue | undefined;
  params: Record<string, ComponentSwitchRuntimeValue>;
} => {
  if (!supportsComponentSwitch(chartType) || !param || !isComponentSwitchCandidate(param) || !options.length) {
    return { value: undefined, params: {} };
  }
  const params = buildComponentSwitchRuntimeParams(param, currentValue, options);
  const value = params[param.name];
  return value === undefined ? { value: undefined, params: {} } : { value, params };
};

const omitComponentSwitchFlag = (param: ParamItem): ParamItem => {
  const inputConfig = param.inputConfig;
  if (!inputConfig || !('componentSwitch' in inputConfig)) return param;
  const nextInputConfig = { ...inputConfig } as Record<string, unknown>;
  delete nextInputConfig.componentSwitch;
  return { ...param, inputConfig: nextInputConfig as ParamItem['inputConfig'] };
};

/** 打开画布或 AI 落盘时收口。不改多选，也不因为选项引用关掉切换。 */
export const sanitizeComponentSwitchParams = (
  chartType: string | undefined,
  params: ParamItem[] | undefined,
): { params: ParamItem[]; warnings: StringParamMigrationWarning[]; changed: boolean } => {
  const source = params || [];
  if (!supportsComponentSwitch(chartType)) {
    let changed = false;
    const warnings: StringParamMigrationWarning[] = [];
    const next = source.map((param) => {
      const inputConfig = param.inputConfig as SwitchableInputConfig | undefined;
      if (inputConfig?.componentSwitch !== true) return param;
      changed = true;
      warnings.push({
        code: 'component_switch_unsupported_chart',
        key: param.name,
        message: 'componentSwitch removed because this chart does not use the main data request',
      });
      return omitComponentSwitchFlag(param);
    });
    return { params: changed ? next : source, warnings, changed };
  }
  const candidates = findComponentSwitchParams(source);
  if (candidates.length <= 1) return { params: source, warnings: [], changed: false };
  const keepName = candidates[0]?.name;
  let changed = false;
  const warnings: StringParamMigrationWarning[] = [];
  const next = source.map((param) => {
    if (!isComponentSwitchCandidate(param) || param.name === keepName) return param;
    changed = true;
    warnings.push({
      code: 'component_switch_extra_dropped',
      key: param.name,
      message: 'componentSwitch removed because the card already has one',
    });
    return omitComponentSwitchFlag(param);
  });
  return { params: changed ? next : source, warnings, changed };
};

export type ComponentSwitchRequestGate = 'ready' | 'pending' | 'blocked';

/**
 * componentSwitch 依赖动态选项时，主数据请求必须等选项就绪并解析出有效参数，
 * 否则会带着空默认值先打一次无效请求（如 server_room_id 必填）。
 */
export const resolveComponentSwitchRequestGate = ({
  hasComponentSwitchParam,
  optionStatus,
  runtimeParams,
}: {
  hasComponentSwitchParam: boolean;
  optionStatus: 'idle' | 'loading' | 'success' | 'error' | 'blocked';
  runtimeParams: Record<string, unknown>;
}): ComponentSwitchRequestGate => {
  if (!hasComponentSwitchParam) return 'ready';
  if (optionStatus === 'idle' || optionStatus === 'loading') return 'pending';
  if (optionStatus === 'blocked') return 'blocked';
  if (optionStatus === 'success' && Object.keys(runtimeParams).length > 0) return 'ready';
  return 'blocked';
};
