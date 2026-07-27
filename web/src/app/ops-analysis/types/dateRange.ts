export const DATE_RANGE_TYPES = [
  'today',
  'yesterday',
  'this_week',
  'last_week',
  'this_month',
  'last_month',
  'last_7_days',
  'last_30_days',
  'last_90_days',
  'custom',
] as const;

export type DateRangeType = (typeof DATE_RANGE_TYPES)[number];

export type DateRangeValue =
  | {
    rangeType: Exclude<DateRangeType, 'custom'>;
    startDate?: never;
    endDate?: never;
  }
  | {
    rangeType: 'custom';
    startDate: string;
    endDate: string;
  };

export type ResolvedDateRange = readonly [string, string];

export const DEFAULT_DATE_RANGE_VALUE: DateRangeValue = {
  rangeType: 'last_7_days',
};
