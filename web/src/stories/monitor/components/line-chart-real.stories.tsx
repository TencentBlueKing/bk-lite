import React from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import LineChart from '@/app/monitor/components/charts/lineChart';
import type { ChartData } from '@/app/monitor/types';
import { createMetricQueryWindow } from '@/app/monitor/components/metric-views/queryWindow';

/**
 * 生产组件 LineChart 的真实渲染 —— 用于验证「报告风」整改效果。
 * 直接渲染 src/app/monitor/components/charts/lineChart.tsx，
 * 不是预览复刻件。多序列 + 阈值线，验证固定色板/细线/渐变填充/
 * 深色 hover/竖向准星 在真实组件里的表现。
 */

function genData(): ChartData[] {
  const start = 1716595200; // 2024-05-25 00:00
  const points = 90;
  const step = 16 * 60;
  const data: ChartData[] = [];
  for (let i = 0; i < points; i++) {
    data.push({
      time: start + i * step,
      value1: 9 + 3 * Math.sin(i / 6) + 2 * Math.sin(i / 2.3) + (i % 17 === 0 ? 5 : 0),
      value2: 6 + 3 * Math.sin(i / 5 + 1) + 1.5 * Math.cos(i / 3),
      value3: 2.5 + 1.2 * Math.sin(i / 4 + 2) + (i % 23 === 0 ? 3 : 0),
      value4: 2 + 0.8 * Math.sin(i / 7),
      value5: 1.2 + 0.6 * Math.cos(i / 5) + (i % 29 === 0 ? 6 : 0),
    } as ChartData);
  }
  return data;
}
const DATA = genData();
const GAP_STEP = 60;
const GAP_START = 1716595200 + GAP_STEP * 4;
const GAP_END = 1716595200 + GAP_STEP * 5;
const GAP_DATA: ChartData[] = Array.from({ length: 9 }, (_, index) => index)
  .filter((index) => index !== 4 && index !== 5)
  .map((index, dataIndex) => ({
    time: 1716595200 + index * GAP_STEP,
    value1: 8 + Math.sin(index / 2),
    seriesMetrics: {
      value1: { instance_id: 'host-a' },
    },
    ...(dataIndex === 0
      ? {
        gapIntervals: [{
          start: GAP_START,
          end: GAP_END,
          duration: GAP_END - GAP_START + GAP_STEP,
          series: [{ metric: { instance_id: 'host-a' }, missing_points: 2 }],
        }],
      }
      : {}),
  }));
const TRAILING_RANGE_START = 1716595200;
const TRAILING_RANGE_END = TRAILING_RANGE_START + 30 * 60;
const TRAILING_GAP_DATA: ChartData[] = [0, 60, 120].map((offset, index) => ({
  time: TRAILING_RANGE_START + offset,
  value1: 8 + index * 0.4,
  seriesMetrics: {
    value1: { instance_id: 'host-a' },
  },
  ...(index === 0
    ? {
      gapIntervals: [{
        start: TRAILING_RANGE_START + 180,
        end: TRAILING_RANGE_END,
        duration: TRAILING_RANGE_END - TRAILING_RANGE_START - 120,
        series: [{ metric: { instance_id: 'host-a' }, missing_points: 28 }],
      }],
    }
    : {}),
}));
const BOUNDARY_RANGE_START = 1716595200;
const BOUNDARY_RANGE_END = BOUNDARY_RANGE_START + 15 * 60;
const BOUNDARY_GAP_DATA: ChartData[] = [600, 660, 720].map((offset, index) => ({
  time: BOUNDARY_RANGE_START + offset,
  value1: 8 + index * 0.4,
  seriesMetrics: {
    value1: { instance_id: 'host-a' },
  },
  ...(index === 0
    ? {
      gapIntervals: [
        {
          start: BOUNDARY_RANGE_START,
          end: BOUNDARY_RANGE_START + 540,
          duration: 600,
          series: [{ metric: { instance_id: 'host-a' }, missing_points: 10 }],
        },
        {
          start: BOUNDARY_RANGE_START + 780,
          end: BOUNDARY_RANGE_END,
          duration: 180,
          series: [{ metric: { instance_id: 'host-a' }, missing_points: 3 }],
        },
      ],
    }
    : {}),
}));
const CLIPPED_LEADING_GAP_DATA: ChartData[] = [600, 660, 720].map((offset, index) => ({
  time: BOUNDARY_RANGE_START + offset,
  value1: 8 + index * 0.4,
  seriesMetrics: {
    value1: { instance_id: 'host-a' },
  },
  ...(index === 0
    ? {
      gapIntervals: [{
        start: BOUNDARY_RANGE_START - 300,
        end: BOUNDARY_RANGE_START + 540,
        duration: 900,
        series: [{ metric: { instance_id: 'host-a' }, missing_points: 15 }],
      }],
    }
    : {}),
}));
const FIXED_HOUR_END_MS = (BOUNDARY_RANGE_START + 60 * 60) * 1000;
const FIXED_HOUR_WINDOW = createMetricQueryWindow(
  { timeRange: [], originValue: 60 },
  FIXED_HOUR_END_MS
)!;
const FIXED_HOUR_SERIES = [
  [28, 34, 40, 46, 52],
  [8, 18, 30, 44],
  [20, 26, 32, 38, 44, 50, 56],
  [12, 24, 36, 48],
].map((minuteOffsets, seriesIndex) => minuteOffsets.map((minute, pointIndex) => ({
  time: BOUNDARY_RANGE_START + minute * 60,
  value1: 2 + seriesIndex + Math.sin(pointIndex),
} as ChartData)));

const meta: Meta<typeof LineChart> = {
  title: 'Monitor/折线图（生产组件）',
  component: LineChart,
  parameters: { layout: 'fullscreen' },
};
export default meta;

type Story = StoryObj<typeof LineChart>;

/** EmptyState —— 空态背景只占绘图区，保留坐标轴所需的上下左右空间。 */
export const EmptyState: Story = {
  render: () => (
    <div style={{ padding: 24, background: 'var(--color-bg-2, #f7fafc)', height: '100vh' }}>
      <div
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
          borderRadius: 8,
          padding: 16,
          height: 240,
        }}
      >
        <LineChart data={[]} unit="%" allowSelect={false} />
      </div>
    </div>
  ),
};

/** ReportedGapBoundary —— 后端缺数边界不扩展到相邻采样点。 */
export const ReportedGapBoundary: Story = {
  render: () => (
    <div style={{ padding: 24, background: 'var(--color-bg-2, #f7fafc)', height: '100vh' }}>
      <div
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
          borderRadius: 8,
          padding: 16,
          height: 240,
        }}
      >
        <LineChart data={GAP_DATA} unit="%" allowSelect={false} />
      </div>
    </div>
  ),
};

/** TrailingGapInSelectedRange —— 数据提前结束时仍展示完整选择范围及尾部缺数。 */
export const TrailingGapInSelectedRange: Story = {
  render: () => (
    <div style={{ padding: 24, background: 'var(--color-bg-2, #f7fafc)', height: '100vh' }}>
      <div
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
          borderRadius: 8,
          padding: 16,
          height: 240,
        }}
      >
        <LineChart
          data={TRAILING_GAP_DATA}
          unit="%"
          allowSelect={false}
          xAxisDomain={[TRAILING_RANGE_START, TRAILING_RANGE_END]}
        />
      </div>
    </div>
  ),
};

/** LeadingAndTrailingGap —— 查询范围两端均无数据时，缺数背景与左右边界对齐。 */
export const LeadingAndTrailingGap: Story = {
  render: () => (
    <div style={{ padding: 24, background: 'var(--color-bg-2, #f7fafc)', height: '100vh' }}>
      <div
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
          borderRadius: 8,
          padding: 16,
          height: 240,
        }}
      >
        <LineChart
          data={BOUNDARY_GAP_DATA}
          unit="%"
          allowSelect={false}
          xAxisDomain={[BOUNDARY_RANGE_START, BOUNDARY_RANGE_END]}
        />
      </div>
    </div>
  ),
};

/** ClippedLeadingGap —— 缺数区从时间窗外延伸进来时，只显示轴内部分。 */
export const ClippedLeadingGap: Story = {
  render: () => (
    <div style={{ padding: 24, background: 'var(--color-bg-2, #f7fafc)', height: '100vh' }}>
      <div
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
          borderRadius: 8,
          padding: 16,
          height: 240,
        }}
      >
        <LineChart
          data={CLIPPED_LEADING_GAP_DATA}
          unit="%"
          allowSelect={false}
          xAxisDomain={[BOUNDARY_RANGE_START, BOUNDARY_RANGE_END]}
        />
      </div>
    </div>
  ),
};

/** FixedOneHourWindow —— 数据覆盖各不相同，四张图仍共享完整、固定的一小时时间轴。 */
export const FixedOneHourWindow: Story = {
  render: () => (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
        gap: 12,
        padding: 24,
        background: 'var(--color-bg-2, #f7fafc)',
        height: '100vh',
      }}
    >
      {FIXED_HOUR_SERIES.map((data, index) => (
        <div
          key={index}
          style={{
            background: 'var(--color-bg-1)',
            border: '1px solid var(--color-border-1)',
            borderRadius: 8,
            padding: 16,
            height: 240,
          }}
        >
          <LineChart
            data={data}
            unit="%"
            allowSelect={false}
            xAxisDomain={FIXED_HOUR_WINDOW.xAxisDomain}
          />
        </div>
      ))}
    </div>
  ),
};

/** LeadingAndTrailingGapDark —— 暗色主题下验证缺数提示仍克制且边界可辨。 */
export const LeadingAndTrailingGapDark: Story = {
  render: () => (
    <div
      className="dark"
      style={{ padding: 24, background: 'var(--color-bg)', height: '100vh' }}
    >
      <div
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
          borderRadius: 8,
          padding: 16,
          height: 240,
        }}
      >
        <LineChart
          data={BOUNDARY_GAP_DATA}
          unit="%"
          allowSelect={false}
          xAxisDomain={[BOUNDARY_RANGE_START, BOUNDARY_RANGE_END]}
        />
      </div>
    </div>
  ),
};

/** MultiSeries —— 验证固定色板 + 细线 + 渐变填充 + 深色 hover */
export const MultiSeries: Story = {
  render: () => (
    <div style={{ padding: 24, background: 'var(--color-bg-2, #f7fafc)', height: '100vh' }}>
      <div
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
          borderRadius: 8,
          padding: 16,
          height: 360,
        }}
      >
        <LineChart data={DATA} unit="%" allowSelect={false} />
      </div>
    </div>
  ),
};

// ─── 边界维度文本 ────────────────────────────────────────────
const LONG_DIM =
  'kubernetes.pod.name=payment-gateway-prod-asia-southeast-1-replicaset-7f8d9c-' +
  'abcdefghijklmnopqrstuvwxyz-0123456789-very-long-segment-that-keeps-going-and-going';
const NEWLINE_DIM = '行一\n行二\n行三\ttab分隔\r回车';
const SPECIAL_DIM = '<script>alert(1)</script> & "引号" \'单引号\' {花括号} 100%';

// 把同一组维度 detail 注入每一行
function withDetails(): ChartData[] {
  return DATA.map((row) => ({
    ...row,
    details: {
      value1: [{ name: 'pod', label: 'pod', value: LONG_DIM }],
      value2: [{ name: 'host', label: 'host', value: NEWLINE_DIM }],
      value3: [{ name: 'svc', label: 'svc', value: SPECIAL_DIM }],
      value4: [{ name: 'zone', label: 'zone', value: `${'维'.repeat(60)}` }],
      value5: [{ name: 'ns', label: 'ns', value: 'default' }],
    },
  })) as ChartData[];
}
const DATA_DETAILS = withDetails();

/** 边界 · 超长/换行/特殊字符维度 —— 验证 tooltip 与维度区 */
export const BoundaryExtremeDimensions: Story = {
  render: () => (
    <div style={{ padding: 24, background: 'var(--color-bg-2, #f7fafc)', height: '100vh' }}>
      <div
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
          borderRadius: 8,
          padding: 16,
          height: 420,
        }}
      >
        <LineChart
          data={DATA_DETAILS}
          unit="%"
          allowSelect={false}
          showDimensionFilter
          showDimensionTable
        />
      </div>
    </div>
  ),
};

/** WithThreshold —— 验证阈值色与序列色互不干扰 */
export const WithThreshold: Story = {
  render: () => (
    <div style={{ padding: 24, background: 'var(--color-bg-2, #f7fafc)', height: '100vh' }}>
      <div
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
          borderRadius: 8,
          padding: 16,
          height: 360,
        }}
      >
        <LineChart
          data={DATA}
          unit="%"
          allowSelect={false}
          threshold={[
            { level: 'critical', value: 14, method: '>' } as any,
            { level: 'warning', value: 10, method: '>' } as any,
          ]}
        />
      </div>
    </div>
  ),
};
