import type { Meta, StoryObj } from '@storybook/nextjs';
import React from 'react';
import ComSingle from './comSingle';
import ComGauge from './comGauge';
import ComLine from './comLine';
import ComBar from './comBar';
import ComTable from './comTable';
import ComBarGauge from './comBarGauge';
import ComStateTimeline from './comStateTimeline';
import ComText from './comText';
import { ValueMappingsConfigSection } from '@/app/ops-analysis/components/valueMappingsConfigSection';
import type { ValueMapping } from '@/app/ops-analysis/utils/valueMapping';
import { useTranslation } from '@/utils/i18n';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';

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

    <Section title="⑦ 表格单元格值映射 — 状态列 0→离线/1→在线（新增）">
      <div
        style={{
          width: 560,
          minHeight: 200,
          border: '1px solid #e8e8e8',
          borderRadius: 8,
          background: '#fff',
          padding: 12,
        }}
      >
        <ComTable
          rawData={[
            { host: 'web-01', status: 1, cpu: 45 },
            { host: 'web-02', status: 0, cpu: 0 },
            { host: 'db-01', status: 1, cpu: 88 },
            { host: 'cache-01', status: 0, cpu: 0 },
          ]}
          loading={false}
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
      </div>
    </Section>

    <Section title="⑧ 值映射配置编辑器 — 可视化加规则（新增）">
      <ValueMappingsEditorDemo />
    </Section>

    <Section title="⑨ 多系列堆叠 — line/bar stacking（新增）">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ fontSize: 12, color: '#8c8c8c' }}>
          入/出流量 折线堆叠（stack: true）
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
            rawData={{
              入流量: [
                ['10:00', 20],
                ['10:05', 35],
                ['10:10', 28],
                ['10:15', 40],
              ],
              出流量: [
                ['10:00', 15],
                ['10:05', 22],
                ['10:10', 30],
                ['10:15', 25],
              ],
            }}
            loading={false}
            config={{ chartType: 'line', stack: true }}
          />
        </div>
      </div>
    </Section>

    <Section title="⑩ 面积填充透明度 — fillOpacity（新增）">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ fontSize: 12, color: '#8c8c8c' }}>
          CPU 趋势 fillOpacity: 0.6（更强填充）
        </div>
        <div
          style={{
            width: 560,
            height: 220,
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
              { name: '10:15', value: 58 },
              { name: '10:20', value: 64 },
            ]}
            loading={false}
            config={{ chartType: 'line', fillOpacity: 0.6 }}
          />
        </div>
      </div>
    </Section>

    <Section title="⑪ Bar gauge — 横向条形量规（新增 P1 面板）">
      {[
        { label: 'CPU 92%', v: 92 },
        { label: '内存 63%', v: 63 },
        { label: '磁盘 24%', v: 24 },
      ].map((it) => (
        <div
          key={it.label}
          style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
        >
          <div style={{ fontSize: 12, color: '#8c8c8c' }}>{it.label}</div>
          <div
            style={{
              width: 240,
              height: 90,
              border: '1px solid #e8e8e8',
              borderRadius: 8,
              background: '#fff',
            }}
          >
            <ComBarGauge
              rawData={{ v: it.v }}
              loading={false}
              config={{
                chartType: 'barGauge',
                selectedFields: ['v'],
                unit: '%',
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
          </div>
        </div>
      ))}
    </Section>

    <Section title="⑬ 表格单元格增强 — 色背景 / 条形量规（新增 P1）">
      <div
        style={{
          width: 560,
          minHeight: 180,
          border: '1px solid #e8e8e8',
          borderRadius: 8,
          background: '#fff',
          padding: 12,
        }}
      >
        <ComTable
          rawData={[
            { host: 'web-01', level: 'P1', usage: 92 },
            { host: 'web-02', level: 'P3', usage: 45 },
            { host: 'db-01', level: 'P0', usage: 78 },
            { host: 'cache-01', level: 'P2', usage: 30 },
          ]}
          loading={false}
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
                  cellThresholdColors: [
                    { value: '80', color: '#fd666d' },
                    { value: '50', color: '#EAB839' },
                    { value: '0', color: '#67a567' },
                  ],
                },
              ],
            },
          }}
        />
      </div>
    </Section>

    <Section title="⑭ Text/Markdown 说明面板（新增 P1）">
      <div
        style={{
          width: 560,
          height: 200,
          border: '1px solid #e8e8e8',
          borderRadius: 8,
          background: '#fff',
        }}
      >
        <ComText
          config={{
            chartType: 'text',
            content:
              '# 运营值班说明\n本面板用于**值班交接**与关键链接。\n\n## 注意事项\n- 一级告警 **15 分钟**内响应\n- 变更窗口：每周二 02:00\n- 详见 [运维手册](https://example.com/runbook)',
          }}
        />
      </div>
    </Section>

    <Section title="⑫ State timeline — 状态随时间分段（新增 P1 面板）">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ fontSize: 12, color: '#8c8c8c' }}>
          服务状态时间线（1→在线绿 / 0→离线红）
        </div>
        <div
          style={{
            width: 560,
            height: 100,
            border: '1px solid #e8e8e8',
            borderRadius: 8,
            background: '#fff',
            padding: 12,
          }}
        >
          <ComStateTimeline
            rawData={[
              ['10:00', 1],
              ['10:05', 1],
              ['10:10', 1],
              ['10:15', 0],
              ['10:20', 0],
              ['10:25', 1],
              ['10:30', 1],
              ['10:35', 2],
              ['10:40', 1],
            ]}
            loading={false}
            config={{
              chartType: 'stateTimeline',
              valueMappings: [
                { type: 'value', value: '1', result: { text: '在线', color: '#67a567' } },
                { type: 'value', value: '0', result: { text: '离线', color: '#fd666d' } },
                { type: 'value', value: '2', result: { text: '降级', color: '#EAB839' } },
              ],
            }}
          />
        </div>
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
