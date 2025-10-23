import { UnitMap } from '@/app/log/types/event';

const TIMEOUT_UNITS: string[] = ['s'];

const M_TIMEOUT_UNITS: string[] = ['ms'];

const NODE_STATUS_MAP: Record<string, string> = {
  normal: 'green',
  inactive: 'yellow',
  unavailable: 'gray',
};

const FUNCTION_LIST: string[] = ['count', 'sum', 'max', 'min', 'avg'];

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
