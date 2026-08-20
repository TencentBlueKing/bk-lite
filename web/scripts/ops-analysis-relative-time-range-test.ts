import assert from 'node:assert/strict';

import {
  formatDataSourceParamValue,
  formatTimeRange,
} from '../src/app/ops-analysis/utils/widgetDataTransform';

const relativeMinutes = 7 * 24 * 60;

assert.deepEqual(
  formatTimeRange({
    start: '2026-07-28T00:00:00.000Z',
    end: '2026-08-04T00:00:00.000Z',
    selectValue: relativeMinutes,
  }),
  { selectValue: relativeMinutes },
  '最近7天必须按统一协议发送 selectValue，由取数网关按当前时刻滚动，不能在前端对齐自然日',
);

assert.deepEqual(
  formatTimeRange({
    selectValue: 15,
    rangePickerVaule: null,
  }),
  { selectValue: 15 },
  '统一筛选 {selectValue:15} 必须原样发出相对协议，不能回落到7天 ISO 起止',
);

assert.deepEqual(
  formatTimeRange({
    selectValue: 0,
    start: '2026-08-19T00:00:00.000Z',
    end: '2026-08-20T00:00:00.000Z',
  }),
  {
    start: '2026-08-19T00:00:00.000Z',
    end: '2026-08-20T00:00:00.000Z',
  },
  '自定义时间范围应发送绝对起止，不带过期的快捷分钟数',
);

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
