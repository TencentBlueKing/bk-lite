import assert from 'node:assert/strict';

import {
  formatDataSourceParamValue,
  formatTimeRange,
} from '../src/app/ops-analysis/utils/widgetDataTransform';

const relativeMinutes = 7 * 24 * 60;
const NativeDate = Date;
let advancingNow = Date.parse('2026-08-04T09:52:43.418Z');

class AdvancingDate extends NativeDate {
  constructor(...args: any[]) {
    if (args.length === 0) {
      super(advancingNow);
      advancingNow += 5;
      return;
    }
    super(args[0]);
  }

  static now() {
    const current = advancingNow;
    advancingNow += 5;
    return current;
  }
}

globalThis.Date = AdvancingDate as DateConstructor;
let range: string[];
try {
  range = formatTimeRange({
    start: '2026-07-28T00:00:00.000Z',
    end: '2026-08-04T00:00:00.000Z',
    selectValue: relativeMinutes,
  });
} finally {
  globalThis.Date = NativeDate;
}

const [start, end] = range;
const startAt = Date.parse(start);
const endAt = Date.parse(end);

assert.equal(
  endAt - startAt,
  relativeMinutes * 60 * 1000,
  '最近7天必须解析为滚动10080分钟，不能对齐自然日边界',
);
assert.equal(end, '2026-08-04T09:52:43.418Z');

const legacyNaturalDaysValue = { mode: 'naturalDays', days: 7 };
const formattedLegacyValue = formatDataSourceParamValue(
  'timeRange',
  legacyNaturalDaysValue,
  { referenceNow: '2026-08-04T12:34:56Z', timezone: 'Asia/Shanghai' },
  (value) => ({ formattedByTimeRangeContract: value }),
);

assert.deepEqual(
  formattedLegacyValue,
  { formattedByTimeRangeContract: legacyNaturalDaysValue },
  'timeRange 请求转换不得绕过时间选择器协议私自识别 naturalDays 对象',
);

console.log('ops analysis relative time range tests passed');
