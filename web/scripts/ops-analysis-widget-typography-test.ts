import assert from 'node:assert/strict';
import { resolveMetricFontSize } from '../src/app/ops-analysis/components/ops-analysis-metric-value';
import { toCanvasPixels } from '../src/app/ops-analysis/components/widget-viewport';

const COMPARE_METRIC_HEIGHT_FILL_RATIO = 0.7;

const resolve = (height: number, scale = 1, heightFillRatio = 0.5) =>
  resolveMetricFontSize({
    width: 480,
    height,
    scale,
    minVisibleFontSize: 18,
    maxVisibleFontSize: 104,
    heightFillRatio,
  });

assert.equal(resolve(120), 60, '仪表盘字号应由可用高度驱动');
assert.equal(resolve(360), 104, '仪表盘大容器应受最大可见字号保护');

const compactScreenFont = resolve(150, 0.5);
const tallScreenFont = resolve(300, 0.5);
assert.equal(compactScreenFont * 0.5, 37.5, '大屏矮容器应按最终可见高度计算');
assert.equal(tallScreenFont * 0.5, 75, '大屏高容器应自然放大');
assert.ok(tallScreenFont > compactScreenFont, '大屏高度变化必须改变字号');

assert.equal(resolve(20, 0.5) * 0.5, 18, '最终可见字号不得低于最小值');
assert.equal(toCanvasPixels(14, 0.5), 28, '大屏固定字号只做一次反向换算');
assert.equal(toCanvasPixels(14, 1), 14, '仪表盘固定字号不应发生换算');

assert.ok(
  Math.abs(
    resolve(42.8125, 1, COMPARE_METRIC_HEIGHT_FILL_RATIO) - 29.96875,
  ) < 0.001,
  '周期对比紧凑卡片的主值字号应更充分利用自身可用高度',
);

console.log('ops-analysis widget typography ok');
