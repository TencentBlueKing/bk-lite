import assert from 'node:assert/strict';
import { ChartDataTransformer } from '../src/app/ops-analysis/utils/chartDataTransform';
import { ChartDataTransformer as PackagedChartDataTransformer } from '../src/app/ops-analysis/components/ops-analysis-widgets/runtime';

const emptyPieData = [
  { name: '未分派', value: 0 },
  { name: '待响应', value: 0 },
  { name: '处理中', value: 0 },
];

assert.deepEqual(
  ChartDataTransformer.validatePieData(emptyPieData, '数据格式不匹配'),
  { isValid: true },
  '结构正确但全为 0 的饼图数据应进入空态，而不是格式错误态',
);
assert.deepEqual(
  PackagedChartDataTransformer.validatePieData(
    emptyPieData,
    '数据格式不匹配',
  ),
  { isValid: true },
  '运营分析组件包应保持相同的全 0 空态语义',
);

assert.equal(
  ChartDataTransformer.validatePieData(
    [{ name: '未分派', value: '不是数字' }],
    '数据格式不匹配',
  ).isValid,
  false,
  '无法转换为数值的饼图数据仍应进入格式错误态',
);

const partiallyNumericPieData = [{ name: '未分派', value: '1abc' }];

assert.equal(
  ChartDataTransformer.validatePieData(
    partiallyNumericPieData,
    '数据格式不匹配',
  ).isValid,
  false,
  '只包含数字前缀的字符串不是合法的饼图数值',
);
assert.equal(
  PackagedChartDataTransformer.validatePieData(
    partiallyNumericPieData,
    '数据格式不匹配',
  ).isValid,
  false,
  '运营分析组件包也必须拒绝只包含数字前缀的字符串',
);

assert.equal(
  ChartDataTransformer.validatePieData(
    [{ name: '未分派', value: -1 }],
    '数据格式不匹配',
  ).isValid,
  false,
  '负数不是合法的饼图数据',
);

console.log('ops-analysis pie empty state ok');
