import type { ParamItem } from '../types/dataSource';
import type {
  RuntimeParamControl,
  RuntimeParamOption,
  RuntimeParamValue,
} from '../types/dashBoard';

export type RuntimeParamControlError =
  | 'missingParam'
  | 'emptyOptions'
  | 'emptyLabel'
  | 'emptyValue'
  | 'duplicateValue'
  | 'invalidDefault';

export interface WidgetRuntimeInteractionProps {
  runtimeParamValue?: RuntimeParamValue;
  onRuntimeParamChange?: (value: RuntimeParamValue) => void;
  errorMessage?: string;
}

export type RuntimeParamControlChartTypePatch =
  | Record<string, never>
  | {
    runtimeParamControlEnabled: false;
    runtimeParamControl: undefined;
  };

export const buildRuntimeParamControlChartTypePatch = (
  chartType: string | undefined,
): RuntimeParamControlChartTypePatch =>
  chartType === 'topN'
    ? {}
    : {
      runtimeParamControlEnabled: false,
      runtimeParamControl: undefined,
    };

export const resolveWidgetRuntimeAuthorizationParams = (
  currentDataSourceParams: ParamItem[] | undefined,
): ParamItem[] => currentDataSourceParams || [];

export type TopNContentState = 'loading' | 'error' | 'empty' | 'rows';

export const buildWidgetRuntimeInteractionProps = (
  chartType: string | undefined,
  props: WidgetRuntimeInteractionProps,
): WidgetRuntimeInteractionProps => (chartType === 'topN' ? props : {});

export const resolveTopNContentState = ({
  loading,
  errorMessage,
  hasRows,
}: {
  loading: boolean;
  errorMessage?: string;
  hasRows: boolean;
}): TopNContentState => {
  if (loading) return 'loading';
  if (errorMessage) return 'error';
  return hasRows ? 'rows' : 'empty';
};

export const isTopNContentReady = (state: TopNContentState) =>
  state === 'rows';

export const getWidgetRuntimeParamCandidates = (params: ParamItem[] = []) =>
  params.filter(
    (item) => item.filterType === 'widget' && Boolean(item.name.trim()),
  );

export const shouldClearUnavailableRuntimeParamControl = (
  params: ParamItem[] | undefined,
  dataSourceResolved: boolean,
  enabled: boolean | undefined,
  hasControl: boolean,
): boolean =>
  dataSourceResolved &&
  getWidgetRuntimeParamCandidates(params).length === 0 &&
  (Boolean(enabled) || hasControl);

const valueKey = (value: RuntimeParamValue) =>
  `${typeof value}:${String(value)}`;

const isValidOptionValue = (value: RuntimeParamValue) =>
  typeof value === 'string' ? Boolean(value.trim()) : Number.isFinite(value);

const getOptionError = (
  options: RuntimeParamOption[],
): RuntimeParamControlError | null => {
  if (!options.length) return 'emptyOptions';
  if (options.some((item) => !item.label.trim())) return 'emptyLabel';
  if (options.some((item) => !isValidOptionValue(item.value))) {
    return 'emptyValue';
  }

  const keys = options.map((item) => valueKey(item.value));
  if (new Set(keys).size !== keys.length) return 'duplicateValue';
  return null;
};

const hasOptionValue = (
  options: RuntimeParamOption[],
  value: RuntimeParamValue,
) => options.some((item) => valueKey(item.value) === valueKey(value));

export const getRuntimeParamSegmentedOptions = (
  control?: RuntimeParamControl,
) =>
  (control?.options || []).map((item) => ({
    label: item.label,
    value: item.value,
  }));

export const hasRuntimeParamSegmentedValue = (
  control: RuntimeParamControl | undefined,
  value: RuntimeParamValue | undefined,
) =>
  value !== undefined &&
  hasOptionValue(control?.options || [], value);

export const validateRuntimeParamControl = (
  control: RuntimeParamControl | undefined,
  params: ParamItem[] = [],
): RuntimeParamControlError | null => {
  if (
    !control ||
    !getWidgetRuntimeParamCandidates(params).some(
      (item) => item.name === control.paramName,
    )
  ) {
    return 'missingParam';
  }

  const optionError = getOptionError(control.options);
  if (optionError) return optionError;
  if (!hasOptionValue(control.options, control.defaultValue)) {
    return 'invalidDefault';
  }
  return null;
};

export const resolveRuntimeParamInitialValue = (
  control: RuntimeParamControl | undefined,
  params: ParamItem[] = [],
): RuntimeParamValue | undefined => {
  if (!control) return undefined;

  const sourceParam = getWidgetRuntimeParamCandidates(params).find(
    (item) => item.name === control.paramName,
  );
  if (!sourceParam || getOptionError(control.options)) return undefined;

  if (hasOptionValue(control.options, control.defaultValue)) {
    return control.defaultValue;
  }

  if (
    (typeof sourceParam.value === 'string' ||
      typeof sourceParam.value === 'number') &&
    hasOptionValue(control.options, sourceParam.value)
  ) {
    return sourceParam.value;
  }

  return control.options[0].value;
};

export const buildWidgetRuntimeParams = (
  control: RuntimeParamControl | undefined,
  activeValue: RuntimeParamValue | undefined,
  params: ParamItem[] = [],
): Record<string, RuntimeParamValue> => {
  if (!control || activeValue === undefined) return {};
  if (getOptionError(control.options)) return {};

  const hasWidgetParam = getWidgetRuntimeParamCandidates(params).some(
    (item) => item.name === control.paramName,
  );
  if (!hasWidgetParam || !hasOptionValue(control.options, activeValue)) {
    return {};
  }

  return { [control.paramName]: activeValue };
};
