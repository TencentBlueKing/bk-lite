import React, { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import MultiThresholdGrid from '@/app/monitor/(pages)/event/strategy/detail/multiThresholdGrid';
import { MetricExpressionRow } from '@/app/monitor/(pages)/event/strategy/detail/metricExpressionTypes';
import { UnitListItem } from '@/app/monitor/types';

/**
 * 生产组件 MultiThresholdGrid。多条件阈值按级别分行：
 * 一行一个级别，格子按常规条件排列；前置条件单独一段。
 */

const UNITS: UnitListItem[] = [
  {
    description: '',
    display_unit: '%',
    is_standalone: true,
    system: '',
    unit_id: 'percent',
    unit_name: 'percent',
    category: '',
  },
  {
    description: '',
    display_unit: '次',
    is_standalone: true,
    system: '',
    unit_id: 'count',
    unit_name: 'count',
    category: '',
  },
];

const row = (
  patch: Partial<MetricExpressionRow> & Pick<MetricExpressionRow, 'ref'>
): MetricExpressionRow => ({
  metricId: 1,
  filters: [],
  groupAlgorithm: 'avg',
  groupBy: ['instance_id'],
  role: 'level',
  source: 'metric',
  thresholdUnit: 'percent',
  ...patch,
});

const levelThreshold = (critical: number, error: number, warning: number) => [
  { level: 'critical', method: '>', value: critical },
  { level: 'error', method: '>', value: error },
  { level: 'warning', method: '>', value: warning },
];

function GridDemo({
  initial,
  className,
}: {
  initial: MetricExpressionRow[];
  className?: string;
}) {
  const [rows, setRows] = useState(initial);
  return (
    <div className={className}>
      <MultiThresholdGrid rows={rows} unitList={UNITS} onChange={setRows} />
    </div>
  );
}

const meta: Meta<typeof MultiThresholdGrid> = {
  title: 'Monitor/多条件阈值表',
  component: MultiThresholdGrid,
};
export default meta;

type Story = StoryObj<typeof MultiThresholdGrid>;

/** 两条常规 + 一条前置条件。 */
export const TwoLevelOneGate: Story = {
  render: () => (
    <div className="bg-[var(--color-bg-2)] p-6">
      <GridDemo
        className="w-[880px]"
        initial={[
          row({
            ref: 'a',
            metricLabel: 'CPU等待IO占比',
            threshold: levelThreshold(20, 12, 3),
          }),
          row({
            ref: 'b',
            metricLabel: 'CPU单核使用率',
            threshold: levelThreshold(120, 110, 50),
          }),
          row({
            ref: 'c',
            metricLabel: '请求数',
            role: 'gate',
            thresholdUnit: 'count',
            threshold: [{ method: '>', value: 100 }],
          }),
        ]}
      />
    </div>
  ),
};

/** 五条常规条件，格子自然折行。 */
export const FiveLevelConditions: Story = {
  render: () => (
    <div className="bg-[var(--color-bg-2)] p-6">
      <GridDemo
        className="w-[760px]"
        initial={['a', 'b', 'c', 'd', 'e'].map((ref, index) =>
          row({
            ref,
            metricLabel: ['CPU等待IO占比', 'CPU单核使用率', '内存使用率', '磁盘繁忙度', '网络重传率'][index],
            threshold: levelThreshold(20 + index, 12 + index, 3 + index),
          })
        )}
      />
    </div>
  ),
};

/** b 缺少错误级，该格为空。 */
export const MissingCell: Story = {
  render: () => (
    <div className="bg-[var(--color-bg-2)] p-6">
      <GridDemo
        className="w-[880px]"
        initial={[
          row({
            ref: 'a',
            metricLabel: 'CPU等待IO占比',
            threshold: levelThreshold(20, 12, 3),
          }),
          row({
            ref: 'b',
            metricLabel: 'CPU单核使用率',
            threshold: [
              { level: 'critical', method: '>', value: 120 },
              { level: 'warning', method: '>', value: 50 },
            ],
          }),
        ]}
      />
    </div>
  ),
};
