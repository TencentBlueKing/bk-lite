import React from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { Form } from 'antd';
import {
  OpsAnalysisBar,
  OpsAnalysisBarGauge,
  OpsAnalysisGauge,
  OpsAnalysisEventTable,
  OpsAnalysisLine,
  OpsAnalysisPie,
  OpsAnalysisSingle,
  OpsAnalysisStateTimeline,
  OpsAnalysisTable,
  OpsAnalysisTextPanel,
  OpsAnalysisTopN,
  OpsAnalysisWidgetErrorState,
} from '@/app/ops-analysis/components/ops-analysis-widgets';
import OpsAnalysisWidgetRenderer from '@/app/ops-analysis/components/ops-analysis-widget-renderer';
import {
  GaugeSettingsSection,
  MetricFieldSelectorFormItem,
  SingleValueSettingsSection,
  ThresholdColorConfigSection,
  ValueFormatConfigSection,
  ValueMapping,
  ValueMappingsConfigSection,
} from '@/app/ops-analysis/components/ops-analysis-config-sections';

const thresholdColors = [
  { value: '80', color: '#fd666d' },
  { value: '50', color: '#EAB839' },
  { value: '0', color: '#67a567' },
];

const configSectionMessages: Record<string, string> = {
  'dashboard.gaugeSettings': '仪表盘设置',
  'dashboard.gaugeMin': '最小值',
  'dashboard.gaugeMax': '最大值',
  'dashboard.gaugeMaxMustGreaterMin': '最大值必须大于最小值',
  'dashboard.gaugeShape': '仪表盘形态',
  'dashboard.gaugeShapeSemicircle': '半圆',
  'dashboard.gaugeShapeCircle': '整圆',
  'dashboard.compareLabel': '对比上周期',
  'dashboard.comparePreviousPeriodTip': '基于同长度上一个时间窗口计算变化比例',
  'dashboard.compareUnavailableTip': '当前数据源未配置唯一时间范围参数，暂不支持对比',
  'topology.nodeConfig.dataSettings': '数据设置',
  'topology.nodeConfig.displayField': '展示字段',
  'topology.nodeConfig.selectAtLeastOneField': '至少选择一个展示字段',
  'topology.nodeConfig.selectDisplayField': '请选择展示字段',
  'topology.nodeConfig.selectDataSourceFirst': '请先选择数据源',
  'topology.nodeConfig.fetchingDataFields': '正在获取字段',
  'topology.nodeConfig.clickRefreshToGetFields': '点击刷新获取字段',
  'topology.nodeConfig.refreshDataFields': '刷新数据字段',
  'topology.nodeConfig.unit': '单位',
  'topology.nodeConfig.customSuffix': '自定义后缀',
  'topology.nodeConfig.conversionFactor': '换算系数',
  'topology.nodeConfig.decimalPlaces': '保留位数',
  'topology.nodeConfig.thresholdColors': '阈值配色',
  'topology.nodeConfig.thresholdWhenValueGte': '当值 >=',
  'topology.nodeConfig.thresholdShow': '时显示',
  'topology.nodeConfig.addThresholdBelow': '在下方添加阈值',
  'topology.nodeConfig.baseThresholdNotRemovable': '基础阈值不可删除',
  'topology.nodeConfig.removeThreshold': '删除阈值',
  'topology.nodeConfig.valueMappings': '值映射',
  'topology.nodeConfig.valueMappingsEmpty': '暂无映射规则，点击下方添加',
  'topology.nodeConfig.valueMappingsResultText': '显示文本',
  'topology.nodeConfig.valueMappingsAdd': '添加映射规则',
  'common.selectMsg': '请选择',
  'common.inputMsg': '请输入',
};

const configSectionT = (key: string, defaultMessage?: string) =>
  configSectionMessages[key] || defaultMessage || key;

const configTreeData = [
  {
    key: 'metrics',
    title: '指标',
    children: [
      { key: 'metrics.cpu', title: 'CPU 使用率', isLeaf: true },
      { key: 'metrics.memory', title: '内存使用率', isLeaf: true },
      { key: 'metrics.latency', title: '响应耗时', isLeaf: true },
    ],
  },
  {
    key: 'status',
    title: '状态',
    children: [{ key: 'status.code', title: '状态码', isLeaf: true }],
  },
];

const valueMappings: ValueMapping[] = [
  { type: 'value', value: '0', result: { text: '离线', color: '#fd666d' } },
  { type: 'value', value: '1', result: { text: '在线', color: '#67a567' } },
];

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
            OpsAnalysisBar
          </h3>
          <div className="space-y-4">
            <div style={{ height: 220 }}>
              <OpsAnalysisBar
                rawData={[
                  { name: 'node-1', value: 32 },
                  { name: 'node-2', value: 58 },
                  { name: 'node-3', value: 86 },
                  { name: 'node-4', value: 47 },
                  { name: 'node-5', value: 73 },
                ]}
                config={{
                  chartType: 'bar',
                  thresholdColors,
                }}
              />
            </div>
            <div style={{ height: 220 }}>
              <OpsAnalysisBar
                rawData={{
                  CPU: [
                    ['cluster-a', 42],
                    ['cluster-b', 60],
                    ['cluster-c', 51],
                  ],
                  Memory: [
                    ['cluster-a', 28],
                    ['cluster-b', 21],
                    ['cluster-c', 31],
                  ],
                }}
                config={{
                  chartType: 'bar',
                  stack: true,
                }}
              />
            </div>
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
            OpsAnalysisLine
          </h3>
          <div className="space-y-4">
            <div style={{ height: 220 }}>
              <OpsAnalysisLine
                rawData={[
                  { name: '10:00', value: 35 },
                  { name: '10:05', value: 52 },
                  { name: '10:10', value: 71 },
                  { name: '10:15', value: 91 },
                  { name: '10:20', value: 84 },
                  { name: '10:25', value: 63 },
                  { name: '10:30', value: 41 },
                ]}
                config={{
                  chartType: 'line',
                  thresholdColors,
                }}
              />
            </div>
            <div style={{ height: 220 }}>
              <OpsAnalysisLine
                rawData={{
                  Ingress: [
                    ['10:00', 20],
                    ['10:05', 35],
                    ['10:10', 28],
                    ['10:15', 40],
                  ],
                  Egress: [
                    ['10:00', 15],
                    ['10:05', 22],
                    ['10:10', 30],
                    ['10:15', 25],
                  ],
                }}
                config={{
                  chartType: 'line',
                  stack: true,
                  fillOpacity: 0.45,
                }}
              />
            </div>
          </div>
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
            OpsAnalysisSingle
          </h3>
          <div className="space-y-4">
            <div style={{ height: 180 }}>
              <OpsAnalysisSingle
                rawData={{ latency: 92 }}
                baselineData={{ latency: 63 }}
                config={{
                  chartType: 'single',
                  selectedFields: ['latency'],
                  unit: 'ms',
                  compare: true,
                  thresholdColors,
                }}
              />
            </div>
            <div style={{ height: 180 }}>
              <OpsAnalysisSingle
                rawData={{ v: 14495514624 }}
                config={{
                  chartType: 'single',
                  selectedFields: ['v'],
                  unitId: 'bytesIEC',
                  thresholdColors: [{ value: '0', color: '#366ce4' }],
                }}
              />
            </div>
            <div style={{ height: 180 }}>
              <OpsAnalysisSingle
                rawData={{ status: 0 }}
                config={{
                  chartType: 'single',
                  selectedFields: ['status'],
                  valueMappings: [
                    { type: 'value', value: '0', result: { text: '离线', color: '#fd666d' } },
                    { type: 'value', value: '1', result: { text: '在线', color: '#67a567' } },
                  ],
                }}
              />
            </div>
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
            OpsAnalysisGauge
          </h3>
          <div className="space-y-4">
            <div style={{ height: 180 }}>
              <OpsAnalysisGauge
                rawData={{ v: 72 }}
                config={{
                  chartType: 'gauge',
                  selectedFields: ['v'],
                  unitId: 'percent',
                  gaugeMin: 0,
                  gaugeMax: 100,
                  gaugeShape: 'semicircle',
                  thresholdColors,
                }}
              />
            </div>
            <div style={{ height: 180 }}>
              <OpsAnalysisGauge
                rawData={{ v: 14495514624 }}
                config={{
                  chartType: 'gauge',
                  selectedFields: ['v'],
                  unitId: 'bytesIEC',
                  gaugeMin: 0,
                  gaugeMax: 17179869184,
                  gaugeShape: 'circle',
                  thresholdColors: [{ value: '0', color: '#366ce4' }],
                }}
              />
            </div>
            <div style={{ height: 180 }}>
              <OpsAnalysisGauge
                rawData={{ v: 0 }}
                config={{
                  chartType: 'gauge',
                  selectedFields: ['v'],
                  gaugeMin: 0,
                  gaugeMax: 1,
                  valueMappings: [
                    { type: 'value', value: '0', result: { text: '离线', color: '#fd666d' } },
                    { type: 'value', value: '1', result: { text: '在线', color: '#67a567' } },
                  ],
                }}
              />
            </div>
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
            OpsAnalysisBarGauge
          </h3>
          <div className="space-y-4">
            <div style={{ height: 180 }}>
              <OpsAnalysisBarGauge
                rawData={{ v: 92 }}
                config={{
                  chartType: 'barGauge',
                  selectedFields: ['v'],
                  unitId: 'percent',
                  gaugeMin: 0,
                  gaugeMax: 100,
                  thresholdColors,
                }}
              />
            </div>
            <div style={{ height: 180 }}>
              <OpsAnalysisBarGauge
                rawData={{ v: 63 }}
                config={{
                  chartType: 'barGauge',
                  selectedFields: ['v'],
                  unitId: 'percent',
                  gaugeMin: 0,
                  gaugeMax: 100,
                  thresholdColors: [{ value: '0', color: '#366ce4' }],
                }}
              />
            </div>
            <div style={{ height: 180 }}>
              <OpsAnalysisBarGauge
                rawData={{ v: 0 }}
                config={{
                  chartType: 'barGauge',
                  selectedFields: ['v'],
                  gaugeMin: 0,
                  gaugeMax: 1,
                  valueMappings: [
                    { type: 'value', value: '0', result: { text: '离线', color: '#fd666d' } },
                    { type: 'value', value: '1', result: { text: '在线', color: '#67a567' } },
                  ],
                }}
              />
            </div>
          </div>
        </section>
      </div>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          OpsAnalysisTable
        </h3>
        <div className="space-y-4">
          <OpsAnalysisTable
            rawData={[
              { host: 'web-01', status: 1, cpu: 45 },
              { host: 'web-02', status: 0, cpu: 0 },
              { host: 'db-01', status: 1, cpu: 88 },
              { host: 'cache-01', status: 0, cpu: 0 },
            ]}
            config={{
              chartType: 'table',
              tableConfig: {
                columns: [
                  { key: 'host', title: '主机', visible: true, order: 0 },
                  {
                    key: 'status',
                    title: '状态',
                    visible: true,
                    order: 1,
                    valueMappings: [
                      { type: 'value', value: '0', result: { text: '离线', color: '#fd666d' } },
                      { type: 'value', value: '1', result: { text: '在线', color: '#67a567' } },
                    ],
                  },
                  { key: 'cpu', title: 'CPU%', visible: true, order: 2 },
                ],
              },
            }}
          />
          <OpsAnalysisTable
            rawData={[
              { host: 'web-01', level: 'P1', usage: 92 },
              { host: 'web-02', level: 'P3', usage: 45 },
              { host: 'db-01', level: 'P0', usage: 78 },
              { host: 'cache-01', level: 'P2', usage: 30 },
            ]}
            config={{
              chartType: 'table',
              tableConfig: {
                columns: [
                  { key: 'host', title: '主机', visible: true, order: 0 },
                  {
                    key: 'level',
                    title: '级别',
                    visible: true,
                    order: 1,
                    cellType: 'colorBackground',
                    valueMappings: [
                      { type: 'value', value: 'P0', result: { color: '#fd666d' } },
                      { type: 'value', value: 'P1', result: { color: '#fd9c40' } },
                      { type: 'value', value: 'P2', result: { color: '#EAB839' } },
                      { type: 'value', value: 'P3', result: { color: '#67a567' } },
                    ],
                  },
                  {
                    key: 'usage',
                    title: '使用率',
                    visible: true,
                    order: 2,
                    cellType: 'gauge',
                    cellMax: 100,
                    cellThresholdColors: thresholdColors,
                  },
                ],
              },
            }}
          />
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[420px_minmax(0,1fr)]">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
            OpsAnalysisPie
          </h3>
          <div style={{ height: 260 }}>
            <OpsAnalysisPie
              rawData={[
                { name: 'checkout', value: 48 },
                { name: 'inventory', value: 26 },
                { name: 'billing', value: 17 },
                { name: 'search', value: 9 },
              ]}
            />
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
            OpsAnalysisEventTable
          </h3>
          <OpsAnalysisEventTable
            rawData={{
              items: [
                {
                  id: 'evt-1',
                  title: 'CPU saturation on web-01',
                  severity: 'critical',
                  status: 'firing',
                  time: '2026-06-26 10:15:00',
                  raw_data: { host: 'web-01', cpu: 97, region: 'cn-shanghai' },
                },
                {
                  id: 'evt-2',
                  title: 'Disk usage on db-01',
                  severity: 'warning',
                  status: 'pending',
                  time: '2026-06-26 10:09:00',
                  raw_data: { host: 'db-01', disk: 81, mount: '/data' },
                },
              ],
              total: 2,
              page: 1,
              page_size: 20,
            }}
            config={{
              chartType: 'eventTable',
              tableConfig: {
                columns: [
                  { key: 'title', title: '事件', visible: true, order: 0, width: 280 },
                  { key: 'severity', title: '级别', visible: true, order: 1, width: 120 },
                  { key: 'status', title: '状态', visible: true, order: 2, width: 120 },
                  { key: 'time', title: '时间', visible: true, order: 3, width: 180 },
                ],
              },
            }}
          />
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_380px]">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
            OpsAnalysisTopN
          </h3>
          <div className="space-y-4">
            <div style={{ height: 260 }}>
              <OpsAnalysisTopN
                rawData={[
                  { service: 'checkout-api', requests: 18642 },
                  { service: 'inventory-sync', requests: 14208 },
                  { service: 'billing-worker', requests: 9876 },
                  { service: 'search-gateway', requests: 8231 },
                  { service: 'alert-dispatcher', requests: 4120 },
                ]}
                config={{
                  chartType: 'topN',
                  topNLabelField: 'service',
                  topNValueField: 'requests',
                }}
              />
            </div>
            <div style={{ height: 240 }}>
              <OpsAnalysisTopN
                rawData={[
                  ['beijing', 428],
                  ['shanghai', 377],
                  ['guangzhou', 231],
                  ['shenzhen', 198],
                ]}
                config={{
                  chartType: 'topN',
                  topNLabelField: '0',
                  topNValueField: '1',
                }}
              />
            </div>
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
            OpsAnalysisStateTimeline
          </h3>
          <div className="space-y-4">
            <div style={{ height: 260 }}>
              <OpsAnalysisStateTimeline
                rawData={[
                  ['10:00', 1],
                  ['10:05', 1],
                  ['10:10', 2],
                  ['10:15', 2],
                  ['10:20', 0],
                  ['10:25', 0],
                  ['10:30', 1],
                  ['10:35', 1],
                ]}
                config={{
                  chartType: 'stateTimeline',
                  valueMappings: [
                    { type: 'value', value: '1', result: { text: '在线', color: '#67a567' } },
                    { type: 'value', value: '2', result: { text: '降级', color: '#EAB839' } },
                    { type: 'value', value: '0', result: { text: '离线', color: '#fd666d' } },
                  ],
                }}
              />
            </div>
            <div style={{ height: 220 }}>
              <OpsAnalysisStateTimeline
                rawData={[
                  ['09:00', 'normal'],
                  ['09:05', 'normal'],
                  ['09:10', 'retrying'],
                  ['09:15', 'retrying'],
                  ['09:20', 'throttled'],
                  ['09:25', 'normal'],
                ]}
                config={{
                  chartType: 'stateTimeline',
                }}
              />
            </div>
          </div>
        </section>
      </div>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          OpsAnalysisTextPanel
        </h3>
        <div className="space-y-4">
          <OpsAnalysisTextPanel
            config={{
              chartType: 'text',
              content: `# 运营值班说明

本面板用于**值班交接**与关键链接。

## 注意事项
- 一级告警需要在 **15 分钟** 内响应
- 变更窗口固定在每周二 02:00
- 详细步骤见 [运维手册](https://example.com/runbook)
`,
            }}
          />
          <OpsAnalysisTextPanel
            config={{
              chartType: 'text',
              content: '',
            }}
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          OpsAnalysisWidgetErrorState
        </h3>
        <div className="grid gap-4 md:grid-cols-2">
          <div style={{ width: 320, height: 220 }}>
            <OpsAnalysisWidgetErrorState message="Data query failed" />
          </div>
          <div style={{ width: 320, height: 220 }}>
            <OpsAnalysisWidgetErrorState message="Unknown component type: eventTableX" />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          OpsAnalysisWidgetRenderer
        </h3>
        <div className="grid gap-4 md:grid-cols-2">
          <div style={{ width: 360, height: 240 }}>
            <OpsAnalysisWidgetRenderer
              chartType="text"
              rawData={null}
              config={{
                chartType: 'text',
                content:
                  '# On-call Notes\n- Primary escalation within 15 minutes\n- Change window: Tuesday 02:00',
              }}
            />
          </div>
          <div style={{ width: 360, height: 240 }}>
            <OpsAnalysisWidgetRenderer
              chartType="unknownWidget"
              rawData={null}
              fallback={(
                <OpsAnalysisWidgetErrorState message="Unknown component type: unknownWidget" />
              )}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <h3 className="text-sm font-semibold text-[var(--color-text-1)]">
          Widget config sections
        </h3>
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <Form layout="vertical">
              <MetricFieldSelectorFormItem
                t={configSectionT}
                selectedDataSource={{ id: 1 }}
                singleValueTreeData={configTreeData}
                selectedField="metrics.cpu"
                loadingSingleValueData={false}
                onFetchSingleValueDataFields={() => {}}
                onSingleValueFieldChange={() => {}}
                readonly={false}
                validationMessage={configSectionT('topology.nodeConfig.selectDisplayField')}
              />
            </Form>

            <Form
              layout="vertical"
              initialValues={{
                unitId: 'percent',
                conversionFactor: 1,
                decimalPlaces: 0,
              }}
            >
              <ValueFormatConfigSection t={configSectionT} width={220} />
            </Form>

            <ThresholdColorConfigSection
              t={configSectionT}
              thresholdColors={thresholdColors}
              onThresholdChange={() => {}}
              onThresholdBlur={() => {}}
              onAddThreshold={() => {}}
              onRemoveThreshold={() => {}}
            />

            <ValueMappingsConfigSection
              t={configSectionT}
              value={valueMappings}
              onChange={() => {}}
            />
          </div>

          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <Form
              layout="vertical"
              initialValues={{
                gaugeMin: 0,
                gaugeMax: 100,
                gaugeShape: 'semicircle',
                unitId: 'percent',
                conversionFactor: 1,
                decimalPlaces: 0,
                valueMappings,
              }}
            >
              <GaugeSettingsSection
                t={configSectionT}
                sectionTitle={configSectionT('dashboard.gaugeSettings')}
                selectedDataSource={{ id: 2, name: 'gauge-ds' }}
                singleValueTreeData={configTreeData}
                selectedFields={['metrics.memory']}
                loadingSingleValueData={false}
                thresholdColors={thresholdColors}
                onFetchSingleValueDataFields={() => {}}
                onSingleValueFieldChange={() => {}}
                onThresholdChange={() => {}}
                onThresholdBlur={() => {}}
                onAddThreshold={() => {}}
                onRemoveThreshold={() => {}}
              />
            </Form>

            <Form
              layout="vertical"
              initialValues={{
                unitId: 'percent',
                conversionFactor: 1,
                decimalPlaces: 0,
                compare: true,
                valueMappings,
              }}
            >
              <SingleValueSettingsSection
                t={configSectionT}
                selectedDataSource={{ id: 3, name: 'single-ds' }}
                singleValueTreeData={configTreeData}
                selectedFields={['metrics.cpu']}
                loadingSingleValueData={false}
                thresholdColors={thresholdColors}
                compareAvailable={true}
                onFetchSingleValueDataFields={() => {}}
                onSingleValueFieldChange={() => {}}
                onThresholdChange={() => {}}
                onThresholdBlur={() => {}}
                onAddThreshold={() => {}}
                onRemoveThreshold={() => {}}
              />
            </Form>
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/OpsAnalysis/Widgets/FamilyOverview',
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
