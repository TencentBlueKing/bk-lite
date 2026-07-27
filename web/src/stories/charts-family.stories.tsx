import type { Meta, StoryObj } from '@storybook/nextjs';
import React from 'react';
import dayjs from 'dayjs';
import { Button, Card, Space, Tag, Typography } from 'antd';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceArea,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts';
import ChartAxisTickLabel from '@/components/chart-axis-tick-label';
import ChartDimensionFilter from '@/components/chart-dimension-filter';
import ChartDimensionTable from '@/components/chart-dimension-table';
import ChartEmptyState from '@/components/chart-empty-state';
import { useChartDragSelection } from '@/components/chart-drag-selection/use-chart-drag-selection';
import ChartLegend from '@/components/chart-legend';
import ChartRendererShell from '@/components/chart-renderer-shell';
import ChartSeriesTooltip from '@/components/chart-series-tooltip';
import ChartSurface from '@/components/chart-surface';
import ChartWithDimensionPanel from '@/components/chart-with-dimension-panel';
import ChartWithSidebarLegend from '@/components/chart-with-sidebar-legend';
import EChartsTooltipCard from '@/components/echarts-tooltip-card';
import HorizontalCategoryBarChart from '@/components/horizontal-category-bar-chart';
import { EChartsLineChart, MiniTrendChart, type MiniTrendChartStyles } from '@/app/monitor/components/monitor-dashboard-widgets';
import SectionHeader from '@/components/section-header';
import StackedBarChart from '@/components/stacked-bar-chart';
import TimeSeriesAreaChartCanvas from '@/components/time-series-area-chart-canvas';
import TimeSeriesBarChart from '@/components/time-series-bar-chart';
import { useChartSeriesState } from '@/hooks/useChartSeriesState';
import TimeSeriesComposedChart, {
  formatCompactAxisValue,
} from '@/components/time-series-composed-chart';

const composedData = [
  {
    _time: '2026-06-25T08:00:00.000Z',
    requests: 1800,
    errors: 24,
    warnings: 42,
  },
  {
    _time: '2026-06-25T08:05:00.000Z',
    requests: 2200,
    errors: 30,
    warnings: 38,
  },
  {
    _time: '2026-06-25T08:10:00.000Z',
    requests: 1950,
    errors: 18,
    warnings: 29,
  },
  {
    _time: '2026-06-25T08:15:00.000Z',
    requests: 2480,
    errors: 33,
    warnings: 47,
  },
];

const panelData = [
  {
    time: 1717200000000,
    value1: 18,
    value2: 12,
  },
  {
    time: 1717203600000,
    value1: 24,
    value2: 17,
  },
  {
    time: 1717207200000,
    value1: 12,
    value2: 9,
  },
];

const panelDetails = {
  value1: [{ label: 'Host', value: 'node-1', name: 'host' }],
  value2: [{ label: 'Host', value: 'node-2', name: 'host' }],
};

const shiftedPanelDetails = {
  value2: [{ label: 'Host', value: 'node-2', name: 'host' }],
  value3: [{ label: 'Host', value: 'node-3', name: 'host' }],
};

const legendData = [
  { name: 'service-a', value: 42 },
  { name: 'service-b', value: 31 },
  { name: 'service-c', value: 18 },
];

const denseLegendData = [
  { name: 'North America - Authentication edge cluster', value: 220 },
  { name: 'APAC - Billing async worker pool', value: 176 },
  { name: 'EMEA - Notification routing queue', value: 103 },
  { name: 'Global - Archive and retention pipeline', value: 68 },
  { name: 'Shared - Search index maintenance', value: 44 },
];

const dragSelectionData = [
  { time: 1719200000, value: 4 },
  { time: 1719203600, value: 7 },
  { time: 1719207200, value: 6 },
  { time: 1719210800, value: 9 },
];

const areaCanvasData = [
  { timestamp: 1717200000, value1: 32, value2: 20 },
  { timestamp: 1717203600, value1: 36, value2: 24 },
  { timestamp: 1717207200, value1: 28, value2: 18 },
  { timestamp: 1717210800, value1: 42, value2: 22 },
  { timestamp: 1717214400, value1: 35, value2: 26 },
];

const stepAxisAreaCanvasData = [
  { step: 1, loss: 0.98, accuracy: 0.72 },
  { step: 2, loss: 0.81, accuracy: 0.78 },
  { step: 3, loss: 0.64, accuracy: 0.84 },
  { step: 4, loss: 0.51, accuracy: 0.89 },
];

const dimensionFilterData = [
  { time: 1719200000, value1: 12, value2: 8, value3: 5 },
  { time: 1719203600, value1: 10, value2: 9, value3: 6 },
];

const dimensionFilterDetails = {
  value1: [{ label: 'region', value: 'ap-south-1' }],
  value2: [{ label: 'region', value: 'us-east-1' }],
  value3: [{ label: 'region', value: 'eu-central-1' }],
};

const dimensionTableData = [
  { time: 1719200000, value1: 12.3, value2: 8.4 },
  { time: 1719203600, value1: 10.1, value2: 6.7 },
  { time: 1719207200, value1: 11.9, value2: 9.2 },
];

const dimensionTableDetails = {
  value1: [{ label: 'region', name: 'region', value: 'ap-south-1' }],
  value2: [{ label: 'region', name: 'region', value: 'us-east-1' }],
};

const miniTrendStyles: MiniTrendChartStyles = {
  miniTrendPlaceholder: 'h-full w-full rounded-[10px] bg-[var(--color-fill-1)]',
};

const miniTrendData = [
  { time: 1719302400, value1: 42 },
  { time: 1719306000, value1: 48 },
  { time: 1719309600, value1: 45 },
  { time: 1719313200, value1: 52 },
  { time: 1719316800, value1: 49 },
  { time: 1719320400, value1: 57 },
];

const horizontalCategoryTheme = {
  axisLine: '#e8e8e8',
  splitLine: '#f0f0f0',
  axisLabel: '#7f92a7',
  tooltipBg: '#ffffff',
  tooltipBorder: '#e8e8e8',
  textPrimary: '#1d2b3a',
  textSecondary: '#5a6d7f',
  primary: '#155AEF',
};

const timeSeriesBarData = [
  { time: 1717200000000, value: 18 },
  { time: 1717203600000, value: 24 },
  { time: 1717207200000, value: 12 },
  { time: 1717210800000, value: 30 },
];

const echartsMetric = {
  id: 1,
  metric_group: 1,
  metric_object: 1,
  name: 'latency',
  type: 'time',
  display_name: 'Latency',
  dimensions: [],
  unit: 'ms',
};

const echartsLineData = [
  {
    time: 1719302400,
    value1: 42,
    value2: 30,
    details: {
      '1719302400': [
        { name: 'primary', label: '主序列', value: '42 ms' },
        { name: 'secondary', label: '辅序列', value: '30 ms' },
      ],
    },
  },
  {
    time: 1719306000,
    value1: 48,
    value2: 34,
    details: {
      '1719306000': [
        { name: 'primary', label: '主序列', value: '48 ms' },
        { name: 'secondary', label: '辅序列', value: '34 ms' },
      ],
    },
  },
  {
    time: 1719309600,
    value1: 45,
    value2: 33,
    details: {
      '1719309600': [
        { name: 'primary', label: '主序列', value: '45 ms' },
        { name: 'secondary', label: '辅序列', value: '33 ms' },
      ],
    },
  },
  {
    time: 1719313200,
    value1: 52,
    value2: 39,
    details: {
      '1719313200': [
        { name: 'primary', label: '主序列', value: '52 ms' },
        { name: 'secondary', label: '辅序列', value: '39 ms' },
      ],
    },
  },
];

const echartsBinaryData = [
  { time: 1719302400, value1: 2_048, value2: 1_024 },
  { time: 1719306000, value1: 4_096, value2: 1_536 },
  { time: 1719309600, value1: 8_192, value2: 2_048 },
  { time: 1719313200, value1: 16_384, value2: 3_072 },
];

interface SeriesDemoRow {
  [key: string]: unknown;
  timestamp: number;
  cpu_value?: number;
  memory_value?: number;
  latency?: number;
  details?: Record<string, Array<{ label: string; value: string }>>;
}

const defaultSeriesData: SeriesDemoRow[] = [
  {
    timestamp: 1710000000,
    cpu_value: 73,
    memory_value: 61,
    details: {
      cpu_value: [{ label: 'Instance', value: 'node-a' }],
      memory_value: [{ label: 'Instance', value: 'node-a' }],
    },
  },
  {
    timestamp: 1710000300,
    cpu_value: 68,
    memory_value: 65,
    details: {
      cpu_value: [{ label: 'Instance', value: 'node-b' }],
      memory_value: [{ label: 'Instance', value: 'node-b' }],
    },
  },
];

const noDetailSeriesData: SeriesDemoRow[] = [
  { timestamp: 1710000000, cpu_value: 22, memory_value: 44 },
  { timestamp: 1710000300, cpu_value: 35, memory_value: 51 },
];

const customMatcherSeriesData: SeriesDemoRow[] = [
  {
    timestamp: 1710000000,
    latency: 18,
    details: {
      latency: [{ label: 'Phase', value: 'inference' }],
    },
  },
  {
    timestamp: 1710000300,
    latency: 24,
    details: {
      latency: [{ label: 'Phase', value: 'training' }],
    },
  },
];

const calculateDimensionMetrics = (rows: Array<Record<string, any>>, key: string) => {
  const values = rows.map((row) => Number(row[key] || 0));
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const avgValue = values.reduce((sum, value) => sum + value, 0) / values.length;
  const latestValue = values[values.length - 1];

  return {
    minValue,
    maxValue,
    avgValue,
    latestValue,
  };
};

const DragSelectionContract = ({
  requireDistinctRange = false,
}: {
  requireDistinctRange?: boolean;
}) => {
  const [selectionText, setSelectionText] = React.useState('No selection yet');
  const selection = useChartDragSelection<number>({
    requireDistinctRange,
    toRange: (start, end) => [
      dayjs(Math.min(start, end) * 1000),
      dayjs(Math.max(start, end) * 1000),
    ],
    onRangeChange: ([start, end]) => {
      setSelectionText(`${start.format('MM-DD HH:mm')} -> ${end.format('MM-DD HH:mm')}`);
    },
    isValidLabel: (label): label is number => typeof label === 'number',
  });

  return (
    <div className="space-y-3">
      <div className="text-xs text-[var(--color-text-2)]">{selectionText}</div>
      <div className="h-[240px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={dragSelectionData}
            onMouseDown={selection.handleMouseDown}
            onMouseMove={selection.handleMouseMove}
            onMouseUp={selection.handleMouseUp}
          >
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="time" />
            <YAxis />
            <Area type="monotone" dataKey="value" stroke="#2f6bff" fill="#2f6bff22" />
            {selection.isDragging &&
              selection.startX !== null &&
              selection.endX !== null && (
              <ReferenceArea
                x1={Math.min(selection.startX, selection.endX)}
                x2={Math.max(selection.startX, selection.endX)}
                fill="rgba(47, 107, 255, 0.14)"
                strokeOpacity={0.3}
              />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

const SeriesStateContract: React.FC<{
  data: SeriesDemoRow[];
  title: string;
  keyMatcher?: (key: string) => boolean;
}> = ({ data, title, keyMatcher }) => {
  const {
    chartKeys,
    colors,
    details,
    hasDimension,
    toggleVisibleArea,
    visibleAreas,
  } = useChartSeriesState<
    SeriesDemoRow,
    Record<string, Array<{ label: string; value: string }>>
  >({
    data,
    keyMatcher,
    generateColor: (() => {
      const palette = ['#2f6bff', '#00b96b', '#faad14', '#ff7a45'];
      let index = 0;
      return () => palette[index++ % palette.length];
    })(),
  });

  return (
    <Card title={title} size="small" className="h-full">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <div>
          <Typography.Text type="secondary">Detected keys</Typography.Text>
          <div className="mt-2 flex flex-wrap gap-2">
            {chartKeys.map((key, index) => (
              <Tag key={key} color={visibleAreas.includes(key) ? colors[index] : 'default'}>
                {key}
              </Tag>
            ))}
          </div>
        </div>

        <div>
          <Typography.Text type="secondary">Visibility state</Typography.Text>
          <div className="mt-2 flex flex-wrap gap-2">
            {chartKeys.map((key) => (
              <Button key={key} size="small" onClick={() => toggleVisibleArea(key)}>
                {visibleAreas.includes(key) ? `Hide ${key}` : `Show ${key}`}
              </Button>
            ))}
          </div>
        </div>

        <div>
          <Typography.Text type="secondary">Has dimension details</Typography.Text>
          <div className="mt-2">
            <Tag color={hasDimension ? 'blue' : 'default'}>
              {hasDimension ? 'true' : 'false'}
            </Tag>
          </div>
        </div>

        <pre className="m-0 overflow-auto rounded bg-[var(--color-fill-1)] p-3 text-xs">
          {JSON.stringify(details, null, 2)}
        </pre>
      </Space>
    </Card>
  );
};

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="RendererShell state contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 md:grid-cols-3">
          <div className="h-[200px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <ChartRendererShell loading={true} loadingClassName="flex h-full items-center justify-center rounded-md bg-[var(--color-bg-1)]" />
          </div>
          <div className="h-[200px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <ChartRendererShell
              error={(
                <div className="flex h-full items-center justify-center rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-bg-1)] px-4 text-center text-sm text-[var(--color-text-2)]">
                  Unknown widget type
                </div>
              )}
            />
          </div>
          <div className="h-[200px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <ChartRendererShell>
              <div className="flex h-full items-center justify-center rounded-md bg-[var(--color-bg-1)] text-sm text-[var(--color-text-2)]">
                Content ready
              </div>
            </ChartRendererShell>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <div className="h-[220px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader spacing="compact" title="Surface with data" titleClassName="text-sm font-medium" />
            <ChartSurface
              hasData={true}
              containerClassName="flex h-[150px] w-full flex-col"
              emptyClassName="flex h-full items-center justify-center rounded-[8px] bg-[var(--color-bg-1)]"
            >
              <div className="flex h-full items-center justify-center rounded-[8px] bg-[var(--color-bg-1)] text-[13px] text-[var(--color-text-2)]">
                Chart content
              </div>
            </ChartSurface>
          </div>

          <div className="h-[220px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader spacing="compact" title="Surface loading" titleClassName="text-sm font-medium" />
            <ChartSurface
              loading
              hasData={false}
              containerClassName="flex h-[150px] w-full flex-col"
              loadingClassName="flex h-full items-center justify-center rounded-[8px] bg-[var(--color-bg-1)]"
              emptyClassName="flex h-full items-center justify-center rounded-[8px] bg-[var(--color-bg-1)]"
              loadingContent={(
                <div
                  className="h-5 w-5 animate-spin rounded-full border-2 border-t-transparent"
                  style={{
                    borderColor: '#155AEF33',
                    borderTopColor: 'transparent',
                  }}
                />
              )}
            >
              <div />
            </ChartSurface>
          </div>

          <div className="h-[220px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader spacing="compact" title="Decorated empty surface" titleClassName="text-sm font-medium" />
            <ChartSurface
              hasData={false}
              containerClassName="flex h-[150px] w-full flex-col"
              emptyClassName="h-full w-full"
              emptyStateProps={{
                variant: 'decorated',
                title: 'No metric samples',
                description: 'Connect a source or widen the selected time range to render this chart.',
              }}
            >
              <div />
            </ChartSurface>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <div className="h-[220px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader spacing="compact" title="Plain empty state" titleClassName="text-sm font-medium" />
            <div className="h-[150px]">
              <ChartEmptyState />
            </div>
          </div>

          <div className="h-[220px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader spacing="compact" title="Compact empty state" titleClassName="text-sm font-medium" />
            <div className="h-[150px]">
              <ChartEmptyState description="No metrics matched the current filter." compact />
            </div>
          </div>

          <div className="h-[220px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader spacing="compact" title="Decorated empty state" titleClassName="text-sm font-medium" />
            <div className="h-[150px]">
              <ChartEmptyState
                variant="decorated"
                title="No chart data"
                description="The selected range has no matching series yet."
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Dimension-aware chart workspace" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="h-[340px]">
            <ChartWithDimensionPanel
              hasData={true}
              emptyClassName="h-full min-h-[240px]"
              chart={(
                <div className="h-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
                  <TimeSeriesComposedChart
                    data={composedData}
                    getXLabel={(item) =>
                      new Date(String(item._time)).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    series={[
                      { name: 'Requests', type: 'bar', dataKey: 'requests', color: '#3b82f6' },
                      {
                        name: 'Errors',
                        type: 'line',
                        dataKey: 'errors',
                        color: '#ef4444',
                        yAxisIndex: 1,
                        showArea: true,
                      },
                      {
                        name: 'Warnings',
                        type: 'line',
                        dataKey: 'warnings',
                        color: '#f59e0b',
                        yAxisIndex: 1,
                        showArea: true,
                      },
                    ]}
                    yAxes={[
                      { formatter: formatCompactAxisValue },
                      { formatter: formatCompactAxisValue },
                    ]}
                  />
                </div>
              )}
              filterProps={{
                data: panelData,
                colors: ['#3b82f6', '#14b8a6'],
                visibleAreas: ['value1', 'value2'],
                details: panelDetails,
                onLegendClick: () => undefined,
                title: 'Dimension',
              }}
            />
          </div>

          <div className="h-[340px]">
            <ChartWithDimensionPanel
              hasData={true}
              containerClassName="flex h-full w-full flex-col"
              emptyClassName="h-full min-h-[240px]"
              chart={(
                <div className="flex h-full min-h-[240px] w-full items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] text-sm text-[var(--color-text-2)]">
                  Primary chart without dimension sidebar
                </div>
              )}
            />
          </div>

          <div className="h-[340px]">
            <ChartWithDimensionPanel
              hasData={true}
              emptyClassName="h-full min-h-[240px]"
              chart={(
                <div className="flex h-full w-full items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] text-sm text-[var(--color-text-2)]">
                  Primary chart slot
                </div>
              )}
              tableProps={{
                data: panelData.map((item) => ({
                  time: item.time,
                  value2: item.value2,
                  value3: item.value1,
                })),
                colors: ['#14b8a6', '#f59e0b'],
                details: shiftedPanelDetails,
                calculateMetrics: (_rows, key) => ({
                  minValue: key === 'value2' ? 9 : 12,
                  maxValue: key === 'value2' ? 17 : 24,
                  avgValue: key === 'value2' ? 12.67 : 18,
                }),
                detailMode: 'columns',
                metricColumns: [
                  { key: 'minValue', title: 'Min' },
                  { key: 'maxValue', title: 'Max' },
                  { key: 'avgValue', title: 'Avg' },
                ],
                scroll: { x: 340, y: 220 },
              }}
            />
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Dimension filter" titleClassName="text-sm font-medium" />
            <div className="h-[280px]">
              <ChartDimensionFilter
                title="Dimension"
                data={dimensionFilterData}
                colors={['#2f6bff', '#faad14', '#00cba6']}
                visibleAreas={['value1', 'value3']}
                details={dimensionFilterDetails}
                onLegendClick={() => undefined}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Dimension filter hidden" titleClassName="text-sm font-medium" />
            <div className="h-[280px]">
              <ChartDimensionFilter
                title="Dimension"
                data={dimensionFilterData}
                colors={['#2f6bff', '#faad14', '#00cba6']}
                visibleAreas={[]}
                details={dimensionFilterDetails}
                onLegendClick={() => undefined}
              />
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Dimension table identifier mode" titleClassName="text-sm font-medium" />
            <div className="h-[280px]">
              <ChartDimensionTable
                data={dimensionTableData}
                colors={['#2f6bff', '#00cba6']}
                details={dimensionTableDetails}
                calculateMetrics={calculateDimensionMetrics}
                detailMode="identifier"
                detailColumnTitle="Identifier"
                metricColumns={[
                  {
                    key: 'minValue',
                    title: 'Min',
                    renderText: (value) => `${Number(value || 0).toFixed(2)} ms`,
                  },
                  {
                    key: 'maxValue',
                    title: 'Max',
                    renderText: (value) => `${Number(value || 0).toFixed(2)} ms`,
                  },
                  {
                    key: 'avgValue',
                    title: 'Avg',
                    renderText: (value) => `${Number(value || 0).toFixed(2)} ms`,
                  },
                ]}
                scroll={{ y: 220 }}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Dimension table detail columns" titleClassName="text-sm font-medium" />
            <div className="h-[280px]">
              <ChartDimensionTable
                data={dimensionTableData}
                colors={['#2f6bff', '#00cba6']}
                details={dimensionTableDetails}
                calculateMetrics={calculateDimensionMetrics}
                detailMode="columns"
                metricColumns={[
                  {
                    key: 'minValue',
                    title: 'Min',
                    renderText: (value) => Number(value || 0).toFixed(2),
                  },
                  {
                    key: 'maxValue',
                    title: 'Max',
                    renderText: (value) => Number(value || 0).toFixed(2),
                  },
                  {
                    key: 'latestValue',
                    title: 'Last',
                    renderText: (value) => Number(value || 0).toFixed(2),
                  },
                ]}
                scroll={{ x: 340, y: 220 }}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Time-series composed chart contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Bar + dual line" titleClassName="text-sm font-medium" />
            <div className="h-[280px]">
              <TimeSeriesComposedChart
                data={composedData}
                getXLabel={(item) =>
                  new Date(String(item._time)).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                series={[
                  { name: 'Requests', type: 'bar', dataKey: 'requests', color: '#3b82f6' },
                  {
                    name: 'Errors',
                    type: 'line',
                    dataKey: 'errors',
                    color: '#ef4444',
                    yAxisIndex: 1,
                    showArea: true,
                  },
                  {
                    name: 'Warnings',
                    type: 'line',
                    dataKey: 'warnings',
                    color: '#f59e0b',
                    yAxisIndex: 1,
                    showArea: true,
                  },
                ]}
                yAxes={[
                  { formatter: formatCompactAxisValue },
                  { formatter: formatCompactAxisValue },
                ]}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Dual axis latency" titleClassName="text-sm font-medium" />
            <div className="h-[280px]">
              <TimeSeriesComposedChart
                data={composedData}
                getXLabel={(item) =>
                  new Date(String(item._time)).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                series={[
                  { name: 'Requests', type: 'bar', dataKey: 'requests', color: '#2563eb' },
                  {
                    name: 'P95',
                    type: 'line',
                    dataKey: 'warnings',
                    color: '#10b981',
                    yAxisIndex: 1,
                    lineWidth: 2.5,
                    showArea: true,
                  },
                ]}
                yAxes={[
                  { formatter: formatCompactAxisValue, minInterval: 1 },
                  { formatter: (value) => `${value.toFixed(value >= 100 ? 0 : 1)} ms` },
                ]}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Line only" titleClassName="text-sm font-medium" />
            <div className="h-[280px]">
              <TimeSeriesComposedChart
                data={composedData}
                getXLabel={(item) =>
                  new Date(String(item._time)).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                series={[
                  {
                    name: 'Errors',
                    type: 'line',
                    dataKey: 'errors',
                    color: '#ef4444',
                    showArea: true,
                  },
                  {
                    name: 'Warnings',
                    type: 'line',
                    dataKey: 'warnings',
                    color: '#f59e0b',
                    showArea: true,
                  },
                ]}
                yAxes={[{ formatter: formatCompactAxisValue, minInterval: 1 }]}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Hidden legend dense axis" titleClassName="text-sm font-medium" />
            <div className="h-[280px]">
              <TimeSeriesComposedChart
                data={composedData}
                legendVisible={false}
                xAxisBoundaryGap={false}
                axisLabelFontSize={10}
                grid={{
                  top: 16,
                  left: 48,
                  right: 16,
                  bottom: 24,
                }}
                getXLabel={(item) =>
                  new Date(String(item._time)).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                series={[
                  {
                    name: 'Requests',
                    type: 'line',
                    dataKey: 'requests',
                    color: '#2563eb',
                    showArea: true,
                  },
                ]}
                yAxes={[{ formatter: formatCompactAxisValue, minInterval: 1 }]}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Sidebar legend layout contract" titleClassName="text-sm font-semibold" />
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-3">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader spacing="compact" title="Vertical list" titleClassName="text-sm font-medium" />
              <div className="h-[220px]">
                <ChartLegend
                  data={legendData}
                  colors={['#2f6bff', '#00b96b', '#faad14']}
                />
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader spacing="compact" title="Vertical with percent" titleClassName="text-sm font-medium" />
              <div className="h-[220px]">
                <ChartLegend
                  data={legendData}
                  colors={['#2f6bff', '#00b96b', '#faad14']}
                  showPercent
                />
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader spacing="compact" title="Horizontal dense legend" titleClassName="text-sm font-medium" />
              <div className="h-[220px]">
                <ChartLegend
                  data={denseLegendData}
                  colors={['#2f6bff', '#00b96b', '#faad14', '#ff7a45', '#8b5cf6']}
                  layout="horizontal"
                />
              </div>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader spacing="compact" title="Table legend long labels" titleClassName="text-sm font-medium" />
              <div className="h-[260px]">
                <ChartLegend
                  data={denseLegendData}
                  colors={['#2f6bff', '#00b96b', '#faad14', '#ff7a45', '#8b5cf6']}
                  variant="table"
                  title="Service"
                />
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader spacing="compact" title="Sidebar responsive/fixed layouts" titleClassName="text-sm font-medium" />
              <div className="space-y-4">
                <div className="h-[260px]">
                  <ChartWithSidebarLegend
                    chart={(
                      <div className="h-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
                        <TimeSeriesComposedChart
                          data={composedData}
                          getXLabel={(item) =>
                            new Date(String(item._time)).toLocaleTimeString([], {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          series={[
                            {
                              name: 'Requests',
                              type: 'line',
                              dataKey: 'requests',
                              color: '#2563eb',
                              showArea: true,
                            },
                            {
                              name: 'Errors',
                              type: 'line',
                              dataKey: 'errors',
                              color: '#ef4444',
                              yAxisIndex: 1,
                            },
                          ]}
                          yAxes={[
                            { formatter: formatCompactAxisValue },
                            { formatter: formatCompactAxisValue },
                          ]}
                        />
                      </div>
                    )}
                    legend={(
                      <ChartLegend
                        data={legendData}
                        colors={['#155AEF', '#10B981', '#F59E0B']}
                        variant="table"
                        title="Dimension"
                      />
                    )}
                    legendMode="responsive"
                    chartPaneClassName="flex-1 min-w-[200px]"
                    legendPaneClassName="ml-2 h-full w-40 flex-shrink-0 min-w-0"
                    surfaceProps={{
                      hasData: true,
                      containerClassName: 'flex h-full w-full overflow-hidden',
                      loadingClassName: 'flex h-full w-full items-center justify-center',
                      emptyClassName: 'flex h-full w-full items-center justify-center',
                    }}
                  />
                </div>

                <div className="h-[220px]">
                  <ChartWithSidebarLegend
                    chart={(
                      <div className="flex h-full items-center justify-center rounded-[8px] bg-[var(--color-bg-1)] text-[13px] text-[var(--color-text-2)]">
                        Chart canvas
                      </div>
                    )}
                    legend={(
                      <ChartLegend
                        data={legendData}
                        colors={['#155AEF', '#10B981', '#F59E0B']}
                        layout="vertical"
                        showPercent
                      />
                    )}
                    legendMode="always"
                    chartPaneClassName="flex-1 min-w-0"
                    surfaceProps={{
                      hasData: true,
                      containerClassName: 'flex h-full w-full',
                      loadingClassName: 'flex h-full w-full items-center justify-center',
                      emptyClassName: 'flex h-full w-full items-center justify-center',
                    }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Micro trend chart contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Multi-point sparkline" titleClassName="text-sm font-medium" />
            <div className="h-16 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <MiniTrendChart
                data={miniTrendData}
                color="#2563eb"
                styles={miniTrendStyles}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Single-point fallback line" titleClassName="text-sm font-medium" />
            <div className="h-16 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <MiniTrendChart
                data={[{ time: 1719302400, value1: 42 }]}
                color="#16a34a"
                styles={miniTrendStyles}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Empty placeholder" titleClassName="text-sm font-medium" />
            <div className="h-16 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <MiniTrendChart
                data={[]}
                color="#94a3b8"
                styles={miniTrendStyles}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Category stacked chart contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Default stacked levels" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <StackedBarChart
                data={[
                  { time: '00:00', critical: 8, warning: 4, info: 2 },
                  { time: '06:00', critical: 6, warning: 7, info: 3 },
                  { time: '12:00', critical: 9, warning: 5, info: 4 },
                  { time: '18:00', critical: 4, warning: 6, info: 5 },
                ]}
                colors={{
                  critical: '#F43B2C',
                  warning: '#FFAD42',
                  info: '#4CAF50',
                }}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Empty compact fallback" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <StackedBarChart data={[]} />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Stack-total axis mode" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <StackedBarChart
                data={[
                  { time: '00:00', critical: 6, warning: 3, error: 1 },
                  { time: '06:00', critical: 2, warning: 5, error: 4 },
                  { time: '12:00', critical: 8, warning: 2, error: 3 },
                  { time: '18:00', critical: 4, warning: 1, error: 2 },
                ]}
                colors={{
                  critical: '#F43B2C',
                  warning: '#FFAD42',
                  error: '#D97007',
                }}
                maxBarSize={80}
                yAxisMode="stack-total"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Horizontal category bar contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Single series" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <HorizontalCategoryBarChart
                theme={horizontalCategoryTheme}
                categories={['Primary cluster', 'Reporting replica', 'Archive node']}
                series={[
                  {
                    data: [92, 61, 24],
                    color: '#155AEF',
                    showLabel: true,
                  },
                ]}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Comparison with legend" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <HorizontalCategoryBarChart
                theme={horizontalCategoryTheme}
                categories={['10.0.0.8', '10.0.0.9', '10.0.0.10']}
                series={[
                  {
                    name: '日志量',
                    data: [320, 180, 94],
                    color: '#155AEF',
                  },
                  {
                    name: '错误数',
                    data: [28, 17, 6],
                    color: '#EF4444',
                  },
                ]}
                showLegend
                categoryLabelWidth={110}
                categoryLabelMaxLength={16}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Ranked metric" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <HorizontalCategoryBarChart
                theme={horizontalCategoryTheme}
                categories={['worker-a', 'worker-b', 'worker-c', 'worker-d']}
                series={[
                  {
                    data: [1280, 980, 760, 420],
                    color: '#36BFFA',
                    showLabel: true,
                    labelFormatter: (value) =>
                      value >= 1000 ? `${(value / 1000).toFixed(1)}k` : `${value}`,
                  },
                ]}
                reverse={false}
                categoryLabelWidth={60}
                categoryLabelMaxLength={12}
                axisLabelFontSize={10}
                gridRight={60}
                valueAxisSplitNumber={4}
                splitLineType="solid"
                valueAxisFormatter={(value) =>
                  value >= 1000 ? `${(value / 1000).toFixed(1)}k` : `${value}`
                }
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Single metric range" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <HorizontalCategoryBarChart
                theme={horizontalCategoryTheme}
                categories={['reward_delta']}
                series={[
                  {
                    data: [-12.84],
                    color: '#155AEF',
                    showLabel: true,
                    labelFormatter: (value) => value.toFixed(2),
                  },
                ]}
                reverse={false}
                showCategoryAxis={false}
                gridTop={10}
                gridRight={40}
                gridBottom={0}
                gridLeft={10}
                axisLabelFontSize={12}
                barMaxWidth={18}
                valueAxisDomain={[-16, 0]}
                valueAxisSplitNumber={4}
                valueAxisFormatter={(value) => value.toFixed(0)}
                valueTooltipFormatter={(value) => value.toFixed(2)}
                valueLabelColor="#155AEF"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Time-series bar chart contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Single series" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <TimeSeriesBarChart
                className="h-full w-full"
                data={timeSeriesBarData}
                emptyClassName="h-full min-h-[220px]"
                renderTooltip={(visible) => (
                  <ChartSeriesTooltip
                    visible={visible}
                    rowAlign="center"
                    renderTitle={(label) => new Date(Number(label)).toLocaleTimeString()}
                    getItems={(payload) => [
                      {
                        key: 'value',
                        color: 'var(--color-primary)',
                        value: payload[0]?.value ?? '--',
                        sortValue: Number(payload[0]?.value ?? 0),
                      },
                    ]}
                  />
                )}
                series={[{ dataKey: 'value', fill: 'var(--color-primary)', width: 20, maxBarSize: 30 }]}
                xAxisTickFormatter={(tick) =>
                  new Date(tick).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                }
                yAxisDomain={[0, 'auto']}
                yAxisTicks={[0, 30]}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Compare series" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <TimeSeriesBarChart
                className="h-full w-full"
                data={timeSeriesBarData.map((item, index) => ({
                  ...item,
                  value1: item.value,
                  value2: item.value + (index % 2 === 0 ? 6 : -4),
                }))}
                emptyClassName="h-full min-h-[220px]"
                renderTooltip={(visible) => (
                  <ChartSeriesTooltip
                    visible={visible}
                    rowAlign="center"
                    renderTitle={(label) => new Date(Number(label)).toLocaleTimeString()}
                    getItems={(payload) =>
                      payload.map((item: any) => ({
                        key: item.dataKey,
                        color: item.color,
                        value: item.value,
                        sortValue: Number(item.value ?? 0),
                      }))
                    }
                  />
                )}
                series={[
                  { dataKey: 'value1', fill: '#3b82f6' },
                  { dataKey: 'value2', fill: '#14b8a6' },
                ]}
                xAxisTickFormatter={(tick) =>
                  new Date(tick).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                }
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Monitor ECharts line contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Default comparison" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <EChartsLineChart
                data={echartsLineData as any}
                metric={echartsMetric as any}
                unit="ms"
                seriesStyles={[
                  { color: '#2563eb', fillOpacity: 0.08, strokeOpacity: 1, strokeWidth: 2.8 },
                  { color: '#f59e0b', fillOpacity: 0.03, strokeOpacity: 0.68, strokeWidth: 2.2 },
                ]}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Binary scale" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <EChartsLineChart
                data={echartsBinaryData as any}
                metric={echartsMetric as any}
                unit="bytes"
                seriesStyles={[
                  { color: '#2563eb', fillOpacity: 0.08, strokeOpacity: 1, strokeWidth: 2.8, unit: 'bytes' },
                  { color: '#14b8a6', fillOpacity: 0.03, strokeOpacity: 0.8, strokeWidth: 2.2, unit: 'bytes' },
                ]}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Empty state" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <EChartsLineChart
                data={[]}
                metric={echartsMetric as any}
                unit="ms"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Time-series area canvas contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Overlay + comparison" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <TimeSeriesAreaChartCanvas
                className="h-full w-full"
                data={areaCanvasData}
                margin={{ top: 10, right: 0, left: 0, bottom: 0 }}
                renderTooltip={(visible) => (
                  <ChartSeriesTooltip
                    visible={visible}
                    renderTitle={(label) => dayjs(Number(label) * 1000).format('YYYY-MM-DD HH:mm')}
                    getItems={(payload) =>
                      payload.map((item: any) => ({
                        key: item.dataKey,
                        color: item.color,
                        value: Number(item.value ?? 0).toFixed(2),
                        sortValue: Number(item.value ?? 0),
                      }))
                    }
                  />
                )}
                series={[
                  {
                    dataKey: 'value1',
                    stroke: '#3b82f6',
                    fill: '#3b82f6',
                    fillOpacity: 0,
                    strokeWidth: 2.5,
                    type: 'monotone',
                    isAnimationActive: false,
                  },
                  {
                    dataKey: 'value2',
                    stroke: '#14b8a6',
                    fill: '#14b8a6',
                    fillOpacity: 0,
                    strokeWidth: 2.5,
                    type: 'monotone',
                    isAnimationActive: false,
                  },
                ]}
                toRangeValue={(label) => dayjs(label * 1000)}
                xAxisDataKey="timestamp"
                xAxisTickFormatter={(tick) => dayjs(tick * 1000).format('HH:mm')}
                overlaysAfterSeries={(
                  <ReferenceArea
                    x1={1717203600}
                    x2={1717207200}
                    strokeOpacity={0}
                    fill="rgba(245, 158, 11, 0.1)"
                  />
                )}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Brush window" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <TimeSeriesAreaChartCanvas
                className="h-full w-full"
                data={areaCanvasData}
                margin={{ top: 10, right: 0, left: 0, bottom: 0 }}
                renderTooltip={(visible) => (
                  <ChartSeriesTooltip
                    visible={visible}
                    renderTitle={(label) => dayjs(Number(label) * 1000).format('YYYY-MM-DD HH:mm')}
                    getItems={(payload) =>
                      payload.map((item: any) => ({
                        key: item.dataKey,
                        color: item.color,
                        value: Number(item.value ?? 0).toFixed(2),
                        sortValue: Number(item.value ?? 0),
                      }))
                    }
                  />
                )}
                series={[
                  {
                    dataKey: 'value1',
                    stroke: '#3b82f6',
                    fill: '#3b82f6',
                    fillOpacity: 0,
                    strokeWidth: 2.5,
                    type: 'monotone',
                    isAnimationActive: false,
                  },
                ]}
                brush={{
                  dataKey: 'timestamp',
                  startIndex: 1,
                  endIndex: 3,
                  height: 30,
                  travellerWidth: 5,
                  stroke: '#8884d8',
                  fill: 'var(--color-bg-1)',
                  onChange: () => undefined,
                  tickFormatter: (tick) => dayjs(tick * 1000).format('HH:mm'),
                  series: [
                    {
                      dataKey: 'value1',
                      stroke: '#3b82f6',
                      fill: '#3b82f6',
                      fillOpacity: 0,
                      type: 'monotone',
                      isAnimationActive: false,
                    },
                  ],
                }}
                toRangeValue={(label) => dayjs(label * 1000)}
                xAxisDataKey="timestamp"
                xAxisTickFormatter={(tick) => dayjs(tick * 1000).format('HH:mm')}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4 xl:col-span-2">
            <SectionHeader spacing="compact" title="Step axis without selection" titleClassName="text-sm font-medium" />
            <div className="h-[240px]">
              <TimeSeriesAreaChartCanvas
                allowSelect={false}
                className="h-full w-full"
                data={stepAxisAreaCanvasData}
                gridVertical={false}
                margin={{ top: 10, right: 0, left: -10, bottom: 0 }}
                renderTooltip={(visible) => (
                  <ChartSeriesTooltip
                    visible={visible}
                    rowAlign="center"
                    renderTitle={(label) => `Step: ${label}`}
                    getItems={(payload) =>
                      payload.map((item: any) => ({
                        key: item.dataKey,
                        color: item.color,
                        description: item.dataKey,
                        value: Number(item.value ?? 0).toFixed(2),
                        sortValue: Number(item.value ?? 0),
                      }))
                    }
                  />
                )}
                series={[
                  {
                    dataKey: 'loss',
                    stroke: '#155AEF',
                    fill: '#155AEF',
                    fillOpacity: 0.1,
                    strokeWidth: 2,
                    type: 'monotone',
                  },
                  {
                    dataKey: 'accuracy',
                    stroke: '#14B8A6',
                    fill: '#14B8A6',
                    fillOpacity: 0.1,
                    strokeWidth: 2,
                    type: 'monotone',
                  },
                ]}
                xAxisDataKey="step"
                xAxisTickFormatter={(tick) => String(tick)}
                xAxisType="number"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Tooltip formatting contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Axis series rows" titleClassName="text-sm font-medium" />
            <EChartsTooltipCard
              title="2026-06-29 14:30"
              rows={[
                {
                  key: 'requests',
                  color: '#2f6bff',
                  markerShape: 'circle',
                  label: 'Requests',
                  value: '128',
                },
                {
                  key: 'errors',
                  color: '#ef4444',
                  markerShape: 'circle',
                  label: 'Errors',
                  value: '7',
                },
              ]}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Square markers" titleClassName="text-sm font-medium" />
            <EChartsTooltipCard
              title="nginx-access"
              rows={[
                {
                  key: 'ingress',
                  color: '#155AEF',
                  markerShape: 'square',
                  label: 'Ingress',
                  value: '2.1k',
                },
                {
                  key: 'egress',
                  color: '#14B8A6',
                  markerShape: 'square',
                  label: 'Egress',
                  value: '1.8k',
                },
              ]}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Descriptive item" titleClassName="text-sm font-medium" />
            <EChartsTooltipCard
              title="Distribution"
              rows={[
                {
                  key: 'warn',
                  color: '#F59E0B',
                  markerShape: 'circle',
                  label: 'Warn',
                  value: '42 (18.4%)',
                },
              ]}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Markerless details" titleClassName="text-sm font-medium" />
            <EChartsTooltipCard
              title="10.0.0.5 -> 10.0.1.8"
              rows={[
                {
                  key: 'source',
                  markerShape: 'none',
                  label: 'Source',
                  value: '10.0.0.5',
                },
                {
                  key: 'target',
                  markerShape: 'none',
                  label: 'Target',
                  value: '10.0.1.8',
                },
                {
                  key: 'bytes',
                  markerShape: 'none',
                  label: 'Flow',
                  value: '2.4 GiB',
                },
              ]}
            />
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Series tooltip rows" titleClassName="text-sm font-medium" />
            <ChartSeriesTooltip
              active
              visible
              label={1719200000}
              payload={[
                {
                  color: '#2f6bff',
                  value: 12.4,
                  payload: {
                    details: {
                      value1: [{ label: 'region', value: 'ap-south-1' }],
                    },
                  },
                  dataKey: 'value1',
                },
                {
                  color: '#00cba6',
                  value: 8.1,
                  payload: {
                    details: {
                      value2: [{ label: 'region', value: 'us-east-1' }],
                    },
                  },
                  dataKey: 'value2',
                },
              ]}
              renderTitle={(label) => `2024-06-24 ${label}`}
              getItems={(currentPayload) =>
                currentPayload.map((item: any) => ({
                  key: item.dataKey,
                  color: item.color,
                  description: item.payload.details[item.dataKey]
                    .map((detail: any) => `${detail.label}: ${detail.value}`)
                    .join(' - '),
                  value: `${Number(item.value).toFixed(2)} ms`,
                  sortValue: Number(item.value),
                }))
              }
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Value-only + axis tick labels" titleClassName="text-sm font-medium" />
            <div className="space-y-4">
              <ChartSeriesTooltip
                active
                visible
                rowAlign="center"
                label={24}
                payload={[
                  {
                    color: '#155AEF',
                    value: 42,
                    dataKey: 'requests',
                  },
                  {
                    color: '#EF4444',
                    value: '--',
                    dataKey: 'errors',
                  },
                ]}
                renderTitle={(label) => `Step: ${label}`}
                getItems={(currentPayload) =>
                  currentPayload.map((item: any) => ({
                    key: item.dataKey,
                    color: item.color,
                    value: item.value,
                    sortValue: typeof item.value === 'number' ? item.value : undefined,
                  }))
                }
              />

              <svg width="220" height="60" viewBox="0 0 220 60" style={{ background: 'var(--color-bg-1)' }}>
                <line x1="180" y1="8" x2="180" y2="52" stroke="var(--color-border)" />
                <ChartAxisTickLabel x={172} y={24} label="42" />
                <ChartAxisTickLabel x={172} y={40} label="123456789" />
                <ChartAxisTickLabel x={120} y={52} dx={2} label="warning-state" textAnchor="middle" />
              </svg>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Interaction + state hook contracts" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Drag selection lifecycle" titleClassName="text-sm font-medium" />
            <DragSelectionContract />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Distinct drag selection" titleClassName="text-sm font-medium" />
            <DragSelectionContract requireDistinctRange />
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SeriesStateContract title="Dimension-aware series state" data={defaultSeriesData} />
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SeriesStateContract title="Plain series state" data={noDetailSeriesData} />
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SeriesStateContract
              title="Custom key matcher"
              data={customMatcherSeriesData}
              keyMatcher={(key) => key === 'latency'}
            />
          </div>
        </div>
      </section>

      <section className="space-y-2 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Storybook structure" titleClassName="text-sm font-semibold" />
        <div className="text-sm text-[var(--color-text-2)]">
          The Charts family is currently governed through stable subtrees for `State/*`, `Dimension/*`, `Legend/*`, `Formatting/*`, `TimeSeries/*`, `Category/*`, and `Interaction/*`.
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Framework/Charts/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1120, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
