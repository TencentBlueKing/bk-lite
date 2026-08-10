import type { Meta, StoryObj } from '@storybook/nextjs';
import React from 'react';
import { expect, waitFor } from 'storybook/test';
import ComSingle from './comSingle';
import ComPie from './comPie';
import ComGauge from './comGauge';
import ComLine from './comLine';
import ComBar from './comBar';
import ComTable from './comTable';
import ComTopN from './comTopN';
import ComponentParamSwitchControl from '../componentParamSwitchControl';
import { ValueMappingsConfigSection } from '@/app/ops-analysis/components/valueMappingsConfigSection';
import type { ValueMapping } from '@/app/ops-analysis/utils/valueMapping';
import { useTranslation } from '@/utils/i18n';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import { WidgetViewportProvider } from '@/app/ops-analysis/components/widget-viewport';
import WidgetState from '@/app/ops-analysis/components/widget-state';

const readMetricVisibleFontSize = (container: HTMLElement) => {
  const value = Array.from(container.querySelectorAll<HTMLElement>('div')).find(
    (element) =>
      element.style.fontSize && element.getAttribute('aria-hidden') !== 'true',
  );

  if (!value) {
    throw new Error('未找到单值字号节点');
  }

  const canvasScale = container.getBoundingClientRect().width / container.offsetWidth;
  return Number.parseFloat(window.getComputedStyle(value).fontSize) * canvasScale;
};

const SingleValueSizingRegressionDemo = () => {
  const screenRenderContext = {
    enabled: true,
    fitScale: 0.5,
    screenDensity: 1,
    screenUiScale: 2,
    widgetDensity: 1,
    widgetUiScale: 2,
  };
  const cases = [
    { id: 'dashboard-compact', label: '仪表盘 / 小', width: 240, height: 120 },
    { id: 'dashboard-large', label: '仪表盘 / 大', width: 600, height: 360 },
    { id: 'screen-compact', label: '大屏 / 矮', width: 480, height: 150, screen: true },
    { id: 'screen-tall', label: '大屏 / 高', width: 480, height: 300, screen: true },
  ];

  return (
    <div className="flex flex-wrap items-start gap-6 bg-[#eef3f8] p-6">
      {cases.map(({ id, label, width, height, screen }) => {
        const scale = screen ? screenRenderContext.fitScale : 1;

        return (
          <div key={id}>
            <div className="mb-2 text-xs text-[#65758b]">{label}</div>
            <div style={{ width: width * scale, height: height * scale }}>
              <div
                data-testid={id}
                className="origin-top-left"
                style={{
                  width,
                  height,
                  transform: `scale(${scale})`,
                  border: '1px solid rgba(101, 126, 160, 0.28)',
                  background: 'rgba(255, 255, 255, 0.72)',
                }}
              >
                <WidgetViewportProvider scale={scale}>
                  <ComSingle
                    rawData={20}
                    loading={false}
                    screenRenderContext={screen ? screenRenderContext : undefined}
                    config={{
                      chartType: 'single',
                      chartThemeMode: screen ? 'screen-light' : undefined,
                      unit: '条',
                      thresholdColors: blueThreshold,
                    }}
                  />
                </WidgetViewportProvider>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

const WidgetStateScalingDemo = () => (
  <div className="flex items-start gap-8 bg-[#eef3f8] p-6">
    <div>
      <div className="mb-2 text-xs text-[#65758b]">仪表盘空态</div>
      <div
        data-testid="dashboard-empty-state"
        className="h-[120px] w-[240px] border border-[#d8e0ea] bg-white"
      >
        <WidgetState description="暂无数据" />
      </div>
    </div>
    <div>
      <div className="mb-2 text-xs text-[#65758b]">大屏空态（画布缩放 0.5）</div>
      <div className="h-[120px] w-[240px]">
        <div
          data-testid="screen-empty-state"
          className="h-[240px] w-[480px] origin-top-left border border-[#315d86] bg-[#0b2942]"
          style={{
            transform: 'scale(0.5)',
            '--screen-empty-color': '#a9bfd1',
          } as React.CSSProperties}
        >
          <WidgetViewportProvider scale={0.5}>
            <WidgetState description="暂无数据" />
          </WidgetViewportProvider>
        </div>
      </div>
    </div>
    <div>
      <div className="mb-2 text-xs text-[#65758b]">全 0 饼图</div>
      <div
        data-testid="zero-pie-state"
        className="h-[120px] w-[240px] border border-[#d8e0ea] bg-white"
      >
        <ComPie
          rawData={[
            { name: '未分派', value: 0 },
            { name: '待响应', value: 0 },
          ]}
          loading={false}
          config={{ chartType: 'pie' }}
        />
      </div>
    </div>
  </div>
);

const ValueMappingsEditorDemo: React.FC = () => {
  const { t } = useTranslation();
  const [rules, setRules] = React.useState<ValueMapping[]>([
    { type: 'value', value: '0', result: { text: '离线', color: '#fd666d' } },
    { type: 'value', value: '1', result: { text: '在线', color: '#67a567' } },
    { type: 'range', from: 80, result: { text: '严重', color: '#fd666d' } },
  ]);
  return (
    <div style={{ width: 640 }}>
      <ValueMappingsConfigSection t={t} value={rules} onChange={setRules} />
      <pre
        style={{
          marginTop: 10,
          fontSize: 11,
          background: '#f5f5f5',
          padding: 8,
          borderRadius: 6,
          color: '#555',
        }}
      >
        {JSON.stringify(rules, null, 2)}
      </pre>
    </div>
  );
};

/**
 * 运营分析组件能力演示（对齐 Grafana）：单位库自动量纲、阈值着色、值映射。
 * 用 mock 数据渲染真实 widget，无需 NATS 数据源。
 */

const Card: React.FC<{
  label: string;
  rawData: unknown;
  config: ValueConfig;
  gauge?: boolean;
}> = ({ label, rawData, config, gauge }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
    <div style={{ fontSize: 12, color: '#8c8c8c' }}>{label}</div>
    <div
      style={{
        width: 220,
        height: 130,
        border: '1px solid #e8e8e8',
        borderRadius: 8,
        background: '#fff',
        padding: 8,
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      }}
    >
      {gauge ? (
        <ComGauge rawData={rawData} config={config} loading={false} />
      ) : (
        <ComSingle rawData={rawData} config={config} loading={false} />
      )}
    </div>
  </div>
);

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({
  title,
  children,
}) => (
  <div style={{ marginBottom: 28 }}>
    <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>{title}</div>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20 }}>{children}</div>
  </div>
);

const blueThreshold = [{ value: '0', color: '#366ce4' }];

const TopNRuntimeDimensionPreview: React.FC<{
  label: string;
  chartThemeMode?: ValueConfig['chartThemeMode'];
  background: string;
}> = ({ label, chartThemeMode, background }) => {
  const [runtimeParamValue, setRuntimeParamValue] = React.useState<
    string | number
  >('instance_type');
  const options = [
    { label: '对象类型', value: 'instance_type' },
    {
      label: '使用部门（跨区域成本归属管理部门）',
      value: 'department',
    },
    { label: '申请人', value: 'user' },
  ];
  const switchParam = {
    name: 'group_by',
    alias_name: 'group_by',
    type: 'string',
    filterType: 'params' as const,
    value: 'instance_type',
    inputConfig: {
      control: 'radio' as const,
      componentSwitch: true,
      optionsSource: { type: 'static' as const, staticItems: options },
    },
  };
  const rawData = [
    { key: 'ECS 云服务器', total_cost: 12680.5 },
    { key: 'RDS 云数据库', total_cost: 8650.25 },
    { key: 'OSS 对象存储', total_cost: 3920 },
  ];
  const config: ValueConfig = {
    chartType: 'topN',
    chartThemeMode,
    topNLabelField: 'key',
    topNValueField: 'total_cost',
    params: { group_by: runtimeParamValue },
    dataSourceParams: [switchParam],
  };

  return (
    <div>
      <div className="mb-2 text-xs text-[#8c8c8c]">{label}</div>
      <div
        className="flex h-[260px] w-[360px] flex-col rounded-lg border border-solid border-[#d9d9d9] p-2"
        style={{ background }}
      >
        <div className="mb-2 flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <h4 className="truncate text-sm font-medium">
              超长云资源费用分布标题（验证窄组件标题优先截断）
            </h4>
          </div>
          <div className="ml-auto max-w-[70%] shrink-0 overflow-x-auto">
            <ComponentParamSwitchControl
              inputConfig={switchParam.inputConfig}
              options={options}
              value={runtimeParamValue}
              onChange={setRuntimeParamValue}
            />
          </div>
        </div>
        <div className="min-h-0 flex-1">
          <ComTopN
            rawData={rawData}
            loading={false}
            dataSource={{
              field_schema: [
                { key: 'key', title: '排行主体', value_type: 'string' },
                {
                  key: 'total_cost',
                  title: '费用合计(元)',
                  value_type: 'number',
                },
              ],
            } as any}
            config={config}
          />
        </div>
      </div>
    </div>
  );
};

const TopNWithRuntimeDimensionDemo: React.FC = () => (
  <div className="flex flex-wrap gap-5 bg-[#f5f7fa] p-6">
    <TopNRuntimeDimensionPreview label="默认主题" background="#fff" />
    <TopNRuntimeDimensionPreview
      label="大屏深色主题"
      chartThemeMode="screen-dark"
      background="#06152b"
    />
  </div>
);

const Showcase = () => (
  <div style={{ padding: 24, background: '#f5f7fa' }}>
    <Section title="① 结构化单位库 — 自动量纲缩放（原始值 → 展示）">
      <Card
        label="bytesIEC：1073741824 → 1 GiB"
        rawData={{ v: 1073741824 }}
        config={{ selectedFields: ['v'], unitId: 'bytesIEC', thresholdColors: blueThreshold }}
      />
      <Card
        label="bytesIEC：1610612736 → 1.5 GiB"
        rawData={{ v: 1610612736 }}
        config={{ selectedFields: ['v'], unitId: 'bytesIEC', thresholdColors: blueThreshold }}
      />
      <Card
        label="时间 ms：90000 → 1.5 m"
        rawData={{ v: 90000 }}
        config={{ selectedFields: ['v'], unitId: 'ms', thresholdColors: blueThreshold }}
      />
      <Card
        label="速率 bps：1250000 → 1.25 Mbps"
        rawData={{ v: 1250000 }}
        config={{ selectedFields: ['v'], unitId: 'bps', thresholdColors: blueThreshold }}
      />
      <Card
        label="计数 short：1234567 → 1.23M"
        rawData={{ v: 1234567 }}
        config={{ selectedFields: ['v'], unitId: 'short', thresholdColors: blueThreshold }}
      />
      <Card
        label="百分比 percent：87.5 → 87.5%"
        rawData={{ v: 87.5 }}
        config={{ selectedFields: ['v'], unitId: 'percent', thresholdColors: blueThreshold }}
      />
    </Section>

    <Section title="② 阈值着色 — 按数值落档变色">
      <Card
        label="CPU 92%（≥80 红）"
        rawData={{ v: 92 }}
        config={{
          selectedFields: ['v'],
          unitId: 'percent',
          thresholdColors: [
            { value: '80', color: '#fd666d' },
            { value: '50', color: '#EAB839' },
            { value: '0', color: '#67a567' },
          ],
        }}
      />
      <Card
        label="CPU 63%（≥50 黄）"
        rawData={{ v: 63 }}
        config={{
          selectedFields: ['v'],
          unitId: 'percent',
          thresholdColors: [
            { value: '80', color: '#fd666d' },
            { value: '50', color: '#EAB839' },
            { value: '0', color: '#67a567' },
          ],
        }}
      />
      <Card
        label="CPU 24%（健康 绿）"
        rawData={{ v: 24 }}
        config={{
          selectedFields: ['v'],
          unitId: 'percent',
          thresholdColors: [
            { value: '80', color: '#fd666d' },
            { value: '50', color: '#EAB839' },
            { value: '0', color: '#67a567' },
          ],
        }}
      />
    </Section>

    <Section title="③ 值映射 — 值 → 文本/颜色（状态码可读化）">
      <Card
        label="0 → 离线（红）"
        rawData={{ s: 0 }}
        config={{
          selectedFields: ['s'],
          valueMappings: [
            { type: 'value', value: '0', result: { text: '离线', color: '#fd666d' } },
            { type: 'value', value: '1', result: { text: '在线', color: '#67a567' } },
          ],
        }}
      />
      <Card
        label="1 → 在线（绿）"
        rawData={{ s: 1 }}
        config={{
          selectedFields: ['s'],
          valueMappings: [
            { type: 'value', value: '0', result: { text: '离线', color: '#fd666d' } },
            { type: 'value', value: '1', result: { text: '在线', color: '#67a567' } },
          ],
        }}
      />
      <Card
        label="区间映射：78 → 预警（黄）"
        rawData={{ s: 78 }}
        config={{
          selectedFields: ['s'],
          valueMappings: [
            { type: 'range', from: 0, to: 59.9, result: { text: '健康', color: '#67a567' } },
            { type: 'range', from: 60, to: 79.9, result: { text: '预警', color: '#EAB839' } },
            { type: 'range', from: 80, result: { text: '严重', color: '#fd666d' } },
          ],
        }}
      />
      <Card
        label="特殊值：null → 无数据"
        rawData={{ s: null }}
        config={{
          selectedFields: ['s'],
          valueMappings: [
            { type: 'special', match: 'null', result: { text: '无数据', color: '#bfbfbf' } },
          ],
        }}
      />
    </Section>

    <Section title="④ 仪表盘 — 单位 + 阈值渐变">
      <Card
        gauge
        label="磁盘使用率 72%"
        rawData={{ v: 72 }}
        config={{
          selectedFields: ['v'],
          unitId: 'percent',
          gaugeMin: 0,
          gaugeMax: 100,
          thresholdColors: [
            { value: '80', color: '#fd666d' },
            { value: '50', color: '#EAB839' },
            { value: '0', color: '#67a567' },
          ],
        }}
      />
      <Card
        gauge
        label="内存 13.5 GiB / bytesIEC"
        rawData={{ v: 14495514624 }}
        config={{
          selectedFields: ['v'],
          unitId: 'bytesIEC',
          gaugeMin: 0,
          gaugeMax: 17179869184,
          thresholdColors: [{ value: '0', color: '#366ce4' }],
        }}
      />
      <Card
        gauge
        label="主机状态 0→离线（值映射）"
        rawData={{ v: 0 }}
        config={{
          selectedFields: ['v'],
          gaugeMin: 0,
          gaugeMax: 1,
          valueMappings: [
            { type: 'value', value: '0', result: { text: '离线', color: '#fd666d' } },
            { type: 'value', value: '1', result: { text: '在线', color: '#67a567' } },
          ],
        }}
      />
    </Section>

    <Section title="⑤ 折线阈值线 — 按阈值在 Y 轴画水平虚线（新增）">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ fontSize: 12, color: '#8c8c8c' }}>
          CPU 趋势 + 阈值线（50 黄 / 80 红）
        </div>
        <div
          style={{
            width: 560,
            height: 240,
            border: '1px solid #e8e8e8',
            borderRadius: 8,
            background: '#fff',
            padding: 12,
          }}
        >
          <ComLine
            rawData={[
              { name: '10:00', value: 35 },
              { name: '10:05', value: 52 },
              { name: '10:10', value: 71 },
              { name: '10:15', value: 91 },
              { name: '10:20', value: 84 },
              { name: '10:25', value: 63 },
              { name: '10:30', value: 41 },
            ]}
            loading={false}
            config={{
              chartType: 'line',
              thresholdColors: [
                { value: '80', color: '#fd666d' },
                { value: '50', color: '#EAB839' },
                { value: '0', color: '#67a567' },
              ],
            }}
          />
        </div>
      </div>
    </Section>

    <Section title="⑥ 柱状阈值线 — 同样支持（新增）">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ fontSize: 12, color: '#8c8c8c' }}>
          各节点负载 + 阈值线（50 黄 / 80 红）
        </div>
        <div
          style={{
            width: 560,
            height: 240,
            border: '1px solid #e8e8e8',
            borderRadius: 8,
            background: '#fff',
            padding: 12,
          }}
        >
          <ComBar
            rawData={[
              { name: 'node-1', value: 32 },
              { name: 'node-2', value: 58 },
              { name: 'node-3', value: 86 },
              { name: 'node-4', value: 47 },
              { name: 'node-5', value: 73 },
            ]}
            loading={false}
            config={{
              chartType: 'bar',
              thresholdColors: [
                { value: '80', color: '#fd666d' },
                { value: '50', color: '#EAB839' },
                { value: '0', color: '#67a567' },
              ],
            }}
          />
        </div>
      </div>
    </Section>

    <Section title="⑦ 值映射配置编辑器 — 可视化加规则（新增）">
      <ValueMappingsEditorDemo />
    </Section>

    <Section title="⑧ 大屏深色主题 — TopN / 表格">
      <div
        style={{
          width: 420,
          height: 220,
          border: '1px solid rgba(48, 198, 255, 0.32)',
          borderRadius: 8,
          background: '#06152b',
          padding: 12,
        }}
      >
        <ComTopN
          rawData={[
            { source_name: 'RESTful', event_count: 9 },
            { source_name: 'Zabbix', event_count: 5 },
            { source_name: 'BlueKing', event_count: 3 },
          ]}
          loading={false}
          dataSource={{
            field_schema: [
              { key: 'source_name', title: '告警源', value_type: 'string' },
              { key: 'event_count', title: '事件数', value_type: 'number' },
            ],
          } as any}
          config={{
            chartType: 'topN',
            chartThemeMode: 'screen-dark',
            topNLabelField: 'source_name',
            topNValueField: 'event_count',
          }}
        />
      </div>
      <div
        style={{
          width: 620,
          height: 260,
          border: '1px solid rgba(48, 198, 255, 0.32)',
          borderRadius: 8,
          background: '#06152b',
          padding: 12,
        }}
      >
        <ComTable
          rawData={[
            { id: 'ALERT-001', name: '数据库连接池耗尽', level: '严重' },
            { id: 'ALERT-002', name: 'API响应超时', level: '错误' },
            { id: 'ALERT-003', name: '磁盘空间不足', level: '严重' },
            { id: 'ALERT-004', name: '内存告警', level: '警告' },
          ]}
          loading={false}
          config={{
            chartType: 'table',
            chartThemeMode: 'screen-dark',
            tableConfig: {
              columns: [
                { key: 'id', title: '告警ID', visible: true, order: 0 },
                { key: 'name', title: '告警名称', visible: true, order: 1 },
                { key: 'level', title: '等级', visible: true, order: 2 },
              ],
            },
          }}
        />
      </div>
    </Section>

  </div>
);

const meta: Meta<typeof Showcase> = {
  title: 'OpsAnalysis/ComponentShowcase',
  component: Showcase,
  parameters: { layout: 'fullscreen' },
};
export default meta;

export const Default: StoryObj<typeof Showcase> = {};

export const TopNWithRuntimeDimension: StoryObj<typeof Showcase> = {
  render: () => <TopNWithRuntimeDimensionDemo />,
};

export const SingleValueSizingRegression: StoryObj<typeof Showcase> = {
  render: () => <SingleValueSizingRegressionDemo />,
  play: async ({ canvasElement }) => {
    await waitFor(() => {
      const getCase = (id: string) =>
        canvasElement.ownerDocument.querySelector<HTMLElement>(
          `[data-testid="${id}"]`,
        );
      const dashboardCompact = getCase('dashboard-compact');
      const dashboardLarge = getCase('dashboard-large');
      const screenCompact = getCase('screen-compact');
      const screenTall = getCase('screen-tall');

      expect(dashboardCompact).not.toBeNull();
      expect(dashboardLarge).not.toBeNull();
      expect(screenCompact).not.toBeNull();
      expect(screenTall).not.toBeNull();
      expect(screenCompact!.getBoundingClientRect().width).toBeCloseTo(240, 1);
      expect(readMetricVisibleFontSize(dashboardLarge!)).toBeGreaterThan(
        readMetricVisibleFontSize(dashboardCompact!) * 1.4,
      );
      expect(readMetricVisibleFontSize(screenTall!)).toBeGreaterThan(
        readMetricVisibleFontSize(screenCompact!) * 1.25,
      );
    });
  },
};

export const WidgetStateScaling: StoryObj<typeof Showcase> = {
  render: () => <WidgetStateScalingDemo />,
  play: async ({ canvasElement }) => {
    await waitFor(() => {
      const dashboardDescription = canvasElement.querySelector<HTMLElement>(
        '[data-testid="dashboard-empty-state"] .ant-empty-description',
      );
      const screenDescription = canvasElement.querySelector<HTMLElement>(
        '[data-testid="screen-empty-state"] .ant-empty-description',
      );
      const zeroPieEmpty = canvasElement.querySelector(
        '[data-testid="zero-pie-state"] .ant-empty',
      );

      expect(dashboardDescription).not.toBeNull();
      expect(screenDescription).not.toBeNull();
      expect(zeroPieEmpty).not.toBeNull();
      expect(window.getComputedStyle(dashboardDescription!).fontSize).toBe('14px');
      expect(window.getComputedStyle(screenDescription!).fontSize).toBe('28px');
      expect(screenDescription!.getBoundingClientRect().height).toBeCloseTo(
        dashboardDescription!.getBoundingClientRect().height,
        1,
      );
    });
  },
};
