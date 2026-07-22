import dayjs, { Dayjs } from 'dayjs';

export type TimeValue = number | [number, number];

export interface TimeSelectorDefaultValue {
  selectValue: number;
  rangePickerVaule: [Dayjs, Dayjs] | null;
}

export const getTimeSelectorDefaultValue = (
  value?: TimeValue,
): TimeSelectorDefaultValue => {
  if (Array.isArray(value) && value.length === 2) {
    return {
      selectValue: 0,
      rangePickerVaule: [dayjs(value[0]), dayjs(value[1])],
    };
  }

  return {
    selectValue: typeof value === 'number' ? value : 10080,
    rangePickerVaule: null,
  };
};

export const getTimeSelectorKey = (value?: TimeValue): string =>
  JSON.stringify(
    Array.isArray(value)
      ? { mode: 'custom', value }
      : { mode: 'relative', value: typeof value === 'number' ? value : 10080 },
  );
