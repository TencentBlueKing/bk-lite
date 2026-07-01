import React from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import LineChart from '@/app/monitor/components/charts/lineChart';
import type { ChartData } from '@/app/monitor/types';

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

const meta: Meta<typeof LineChart> = {
  title: 'Monitor/折线图（生产组件）',
  component: LineChart,
  parameters: { layout: 'fullscreen' },
};
export default meta;

type Story = StoryObj<typeof LineChart>;

/** 多序列 —— 验证固定色板 + 细线 + 渐变填充 + 深色 hover */
export const 多序列: Story = {
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
export const 边界_极端维度: Story = {
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

/** 带阈值线 —— 验证阈值色与序列色互不干扰 */
export const 带阈值: Story = {
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
