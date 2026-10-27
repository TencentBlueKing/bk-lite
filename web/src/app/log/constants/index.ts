import { UnitMap } from '@/app/log/types/event';

const TIMEOUT_UNITS: string[] = ['s'];

const M_TIMEOUT_UNITS: string[] = ['ms'];

const NODE_STATUS_MAP: Record<string, string> = {
  normal: 'green',
  inactive: 'yellow',
  unavailable: 'gray',
};

export interface AggregateFunctionOption {
  value: string;
  labelKey: string;
  needsField: boolean;
  unitKey?: string;
  comparable?: boolean;
  needsQuantile?: boolean;
  needsFilter?: boolean;
}

export interface LabeledOption {
  value: string;
  labelKey: string;
}

const FUNCTION_LIST: AggregateFunctionOption[] = [
  { value: 'count', labelKey: 'log.event.funcCount', needsField: true, comparable: true },
  { value: 'sum', labelKey: 'log.event.funcSum', needsField: true, comparable: true },
  { value: 'max', labelKey: 'log.event.funcMax', needsField: true, comparable: true },
  { value: 'min', labelKey: 'log.event.funcMin', needsField: true, comparable: true },
  { value: 'avg', labelKey: 'log.event.funcAvg', needsField: true, comparable: true },
  {
    value: 'count_rate',
    labelKey: 'log.event.funcCountRate',
    needsField: false,
    unitKey: 'log.event.countRateUnit',
    comparable: false,
  },
  {
    value: 'count_uniq',
    labelKey: 'log.event.funcCountUniq',
    needsField: true,
    comparable: true,
  },
  {
    value: 'quantile',
    labelKey: 'log.event.funcQuantile',
    needsField: true,
    needsQuantile: true,
    comparable: true,
  },
  {
    value: 'ratio',
    labelKey: 'log.event.funcRatio',
    needsField: false,
    needsFilter: true,
    comparable: false,
  },
  {
    value: 'bytes_rate',
    labelKey: 'log.event.funcBytesRate',
    needsField: false,
    unitKey: 'log.event.bytesRateUnit',
    comparable: false,
  },
];

const COMPARE_KIND_LIST: LabeledOption[] = [
  { value: 'absolute', labelKey: 'log.event.compareKindAbsolute' },
  { value: 'delta', labelKey: 'log.event.compareKindDelta' },
  { value: 'percent', labelKey: 'log.event.compareKindPercent' },
];

const COMPARE_TARGET_LIST: LabeledOption[] = [
  { value: 'previous_window', labelKey: 'log.event.compareToPreviousWindow' },
  { value: 'offset_1h', labelKey: 'log.event.compareToOffset1h' },
  { value: 'offset_24h', labelKey: 'log.event.compareToOffset24h' },
  { value: 'offset_7d', labelKey: 'log.event.compareToOffset7d' },
];

const QUANTILE_LIST = [0.5, 0.9, 0.95, 0.99];

const SCHEDULE_UNIT_MAP: UnitMap = {
  minMin: 1,
  minMax: 59,
  hourMin: 1,
  hourMax: 23,
  dayMin: 1,
  dayMax: 1,
};

const LEVEL_MAP: Record<string, string> = {
  critical: '#F43B2C',
  error: '#D97007',
  warning: '#FFAD42',
};

export {
  TIMEOUT_UNITS,
  NODE_STATUS_MAP,
  M_TIMEOUT_UNITS,
  FUNCTION_LIST,
  COMPARE_KIND_LIST,
  COMPARE_TARGET_LIST,
  QUANTILE_LIST,
  SCHEDULE_UNIT_MAP,
  LEVEL_MAP,
};
