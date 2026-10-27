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
}

const FUNCTION_LIST: AggregateFunctionOption[] = [
  { value: 'count', labelKey: 'log.event.funcCount', needsField: true },
  { value: 'sum', labelKey: 'log.event.funcSum', needsField: true },
  { value: 'max', labelKey: 'log.event.funcMax', needsField: true },
  { value: 'min', labelKey: 'log.event.funcMin', needsField: true },
  { value: 'avg', labelKey: 'log.event.funcAvg', needsField: true },
  {
    value: 'count_rate',
    labelKey: 'log.event.funcCountRate',
    needsField: false,
    unitKey: 'log.event.countRateUnit',
  },
  {
    value: 'count_delta',
    labelKey: 'log.event.funcCountDelta',
    needsField: false,
  },
];

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
  SCHEDULE_UNIT_MAP,
  LEVEL_MAP,
};
