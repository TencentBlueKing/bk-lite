import React from 'react';
import dayjs from 'dayjs';
import type { Meta, StoryObj } from '@storybook/react';
import { DatabaseOutlined } from '@ant-design/icons';
import { Button, Input, Segmented, Select, Tag } from 'antd';
import {
  CloseOutlined,
  HolderOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import CodeEditor from '@/components/code-editor';
import CodeSnippet from '@/components/code-snippet';
import GuideStepPanel from '@/components/guide-step-panel';
import MonitorAlertTypeBadge from '@/components/monitor-alert-type-badge';
import MonitorIntegrationAccessBadge from '@/components/monitor-integration-access-badge';
import MonitorIntegrationConfigState from '@/components/monitor-integration-config-state';
import MonitorLazyMetricItem from '@/components/monitor-lazy-metric-item';

const displayFieldsPluginOptions = [
  { label: '主机（Telegraf）', value: 'telegraf' },
  { label: 'Windows WMI', value: 'wmi' },
  { label: '主机远程采集（Telegraf）', value: 'remote' },
];

const displayFieldsMetricOptions = [
  { label: 'CPU使用率', value: 'cpu_usage' },
  { label: '节点信息', value: 'node_info' },
];

const displayFieldsFieldOptions = [
  'collector_ip',
  'model',
  'os_name',
  'agent_id',
];

function DisplayFieldsBindingRow({ field }: { field?: string }) {
  return (
    <div className="flex items-center gap-2 pl-6">
      <Select className="flex-1" value="telegraf" options={displayFieldsPluginOptions} />
      <Select
        className="flex-1"
        value={field ? 'node_info' : 'cpu_usage'}
        options={displayFieldsMetricOptions}
      />
      {field && (
        <Input
          className="flex-1"
          value={field}
          addonAfter={
            <Button type="link" size="small" className="px-0">
              选择字段
            </Button>
          }
        />
      )}
      <Button type="text" danger icon={<CloseOutlined />} />
    </div>
  );
}

function DisplayFieldsColumnBlock({
  title,
  tag,
  field,
}: {
  title: string;
  tag: string;
  field?: string;
}) {
  return (
    <div className="rounded border border-[#d9d9d9] bg-[#f5f7fa] p-3">
      <div className="mb-2 flex items-center gap-2">
        <HolderOutlined className="cursor-move text-[#8c8c8c]" />
        <Input className="flex-1" value={title} />
        <Tag color={field ? 'geekblue' : 'blue'}>{tag}</Tag>
        <Button type="text" danger icon={<CloseOutlined />} />
      </div>
      <div className="space-y-2">
        <DisplayFieldsBindingRow field={field} />
        <DisplayFieldsBindingRow field={field} />
      </div>
      <Button
        type="dashed"
        size="small"
        icon={<PlusOutlined />}
        className="ml-6 mt-2"
      >
        添加指标
      </Button>
    </div>
  );
}

function DisplayFieldsModalPreview() {
  return (
    <div className="relative min-h-[760px] bg-[#eef2f6] p-8">
      <div className="mx-auto w-[900px] rounded bg-white shadow-[0_12px_32px_rgba(0,0,0,0.18)]">
        <div className="flex h-14 items-center justify-between border-b border-[#edf0f5] px-5">
          <strong>展示指标配置 - 主机</strong>
          <CloseOutlined className="text-[#8c8c8c]" />
        </div>
        <div className="p-5">
          <div className="mb-3 flex justify-end gap-2">
            <Button icon={<PlusOutlined />}>添加指标列</Button>
            <Button icon={<PlusOutlined />}>添加展示列</Button>
          </div>
          <div className="space-y-3">
            <DisplayFieldsColumnBlock title="CPU使用率" tag="指标列" />
            <DisplayFieldsColumnBlock title="采集节点IP" tag="展示列" field="collector_ip" />
            <DisplayFieldsColumnBlock title="设备型号" tag="展示列" field="model" />
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-[#edf0f5] px-5 py-4">
          <Button>取消</Button>
          <Button type="primary">确认</Button>
        </div>
      </div>
      <div className="absolute left-[610px] top-[545px] w-[260px] rounded border border-[#edf0f5] bg-white p-1 shadow-[0_8px_24px_rgba(0,0,0,0.12)]">
        <div className="max-h-[240px] overflow-y-auto">
          {displayFieldsFieldOptions.map((field) => (
            <button
              key={field}
              type="button"
              className={`block min-h-8 w-full rounded px-3 text-left text-sm leading-8 ${
                field === 'collector_ip'
                  ? 'bg-[#e6f4ff] text-[#1677ff]'
                  : 'text-[#262626]'
              }`}
            >
              {field}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
import LineChart from '@/components/monitor-line-chart';
import MonitorObjectIcon, { DEFAULT_OBJECT_ICON } from '@/components/monitor-object-icon';
import MonitorObjectWorkspaceShell from '@/components/monitor-object-workspace-shell';
import MonitorReportingStatusBadge from '@/components/monitor-reporting-status-badge';
import ManagementTableShell from '@/components/management-table-shell';
import PageHeaderShell from '@/components/page-header-shell';
import SearchActionBar from '@/components/search-action-bar';
import SectionHeader from '@/components/section-header';
import {
  DashboardInstanceCard,
  DashboardPageHeader,
  DetailPanel,
  StatCard,
  type DashboardInstanceCardStyles,
  type DashboardPageHeaderStyles,
  type DetailPanelStyles,
  type StatCardStyles,
} from '@/components/monitor-dashboard-widgets';
import type { ChartData } from '@/components/monitor-dashboard-widgets/types';

const headerStyles: DashboardPageHeaderStyles = {
  pageTitleRow:
    'flex flex-wrap items-center justify-between gap-4 rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5',
  titleBlock: 'min-w-0',
  title: 'm-0 text-[22px] font-semibold text-[var(--color-text-1)]',
  controlsWrap: 'flex flex-wrap items-center gap-3',
  modeTabs:
    'inline-flex items-center rounded-[12px] bg-[var(--color-fill-1)] p-1',
  modeTab:
    'rounded-[10px] px-3 py-1.5 text-[13px] text-[var(--color-text-2)] transition',
  modeTabActive:
    'bg-[var(--color-bg-1)] text-[var(--color-text-1)] shadow-sm',
  toolbarTimeSelector: 'min-w-[458px]',
  toolbarBackBtn: 'shrink-0',
  actionButtons: 'flex items-center',
};

const instanceCardStyles: DashboardInstanceCardStyles = {
  instanceCard:
    'flex flex-wrap items-center justify-between gap-4 rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5',
  instanceCardFull: 'items-start',
  instanceMain: 'flex min-w-0 items-center gap-4',
  instanceIcon:
    'flex h-12 w-12 items-center justify-center rounded-[14px] bg-[var(--color-fill-1)] text-[20px] text-[var(--color-primary)]',
  instanceInfo: 'min-w-0',
  meta: 'flex flex-wrap items-center gap-2 text-[13px] text-[var(--color-text-2)]',
  instanceName: 'text-[18px] font-semibold text-[var(--color-text-1)]',
  instanceMetaDivider: 'text-[var(--color-border-2)]',
  instanceActions: 'flex flex-wrap items-center gap-3',
  inlineInstanceSelector:
    'min-w-[240px] rounded-[12px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-2',
  instanceSelectorLabel: 'text-[13px] text-[var(--color-text-3)]',
  toolbarTimeSelector: 'min-w-[458px]',
};

const detailPanelStyles: DetailPanelStyles = {
  panel: 'rounded-[18px] border border-[var(--color-border-1)] bg-transparent',
  detailCard:
    'rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5 shadow-sm',
  panelHeading: 'mb-4 flex flex-col gap-1',
  panelTitle: 'm-0 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelTitleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  panelSubTitle: 'text-[13px] leading-5 text-[var(--color-text-3)]',
  detailRowsFill: 'space-y-3',
  titleWithGuide:
    'inline-flex items-center gap-2 text-[16px] font-semibold text-[var(--color-text-1)]',
  metricGuideIcon:
    'cursor-help text-[13px] text-[var(--color-text-3)] hover:text-[var(--color-primary)]',
  metricGuideTooltip:
    'max-w-[320px] rounded-[12px] bg-white p-3 shadow-[0_8px_24px_rgba(15,23,42,0.12)]',
  metricGuideTooltipRow:
    'mb-2 flex flex-col gap-1 text-[12px] leading-5 text-[var(--color-text-2)] last:mb-0',
};

const statCardStyles: StatCardStyles = {
  statCard:
    'flex min-h-[188px] flex-col overflow-hidden rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-5 shadow-[0_8px_24px_rgba(15,23,42,0.04)]',
  statHeader: 'flex items-start justify-between gap-3',
  statLabel: 'text-[15px] font-semibold leading-[1.35] text-[var(--color-text-1)]',
  statIcon:
    'flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-[var(--color-fill-1)] text-[18px]',
  statBody: 'mt-4 flex min-h-0 flex-col gap-2',
  statValue:
    'inline-flex min-h-[40px] flex-wrap items-baseline gap-1 text-[32px] font-semibold leading-none text-[var(--color-text-1)]',
  statUnit: 'text-[14px] font-medium text-[var(--color-text-3)]',
  statCompare:
    'flex min-h-[20px] flex-wrap items-center gap-2 text-[13px] font-medium text-[var(--color-text-2)]',
  statCompareFlat: '',
  statComparePositive: '',
  statCompareNegative: '',
  statCompareLabel: 'text-[var(--color-text-3)]',
  statCompareValue: 'inline-flex items-center gap-1',
  statMeta:
    'flex min-h-[22px] flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[var(--color-text-2)]',
  statExtra: 'mt-auto pt-3',
  miniTrend: 'mt-auto h-[56px] overflow-hidden rounded-[10px] pt-3',
  miniTrendPlaceholder: 'h-full w-full rounded-[10px] bg-[var(--color-fill-1)]',
};

const trendData: ChartData[] = [
  { time: 1719302400, value1: 42 },
  { time: 1719306000, value1: 48 },
  { time: 1719309600, value1: 45 },
  { time: 1719313200, value1: 52 },
  { time: 1719316800, value1: 49 },
  { time: 1719320400, value1: 57 },
];

const selectorOptions = [
  {
    label: 'db-prod-01',
    value: 'db-prod-01',
    searchTokens: ['db-prod-01', 'mysql', '10.0.0.21'],
  },
  {
    label: 'db-prod-02',
    value: 'db-prod-02',
    searchTokens: ['db-prod-02', 'mysql', '10.0.0.22'],
  },
];

const objectTreeData = [
  {
    key: 'host',
    title: 'Host',
    children: [
      { key: '1', title: 'Linux Host', label: 'Linux Host', children: [] },
      { key: '2', title: 'Windows Host', label: 'Windows Host', children: [] },
    ],
  },
  {
    key: 'container',
    title: 'Container',
    children: [
      { key: '3', title: 'Pod', label: 'Pod', children: [] },
      { key: '4', title: 'Node', label: 'Node', children: [] },
    ],
  },
];

const metricCardItem = {
  id: 101,
  display_name: 'CPU Usage',
  display_description: 'Metric card with lazy viewport loading behavior',
  displayUnit: '%',
  viewData: [
    {
      date: '2026-07-01T00:00:00Z',
      cpu_usage: 32,
    },
    {
      date: '2026-07-01T00:05:00Z',
      cpu_usage: 46,
    },
    {
      date: '2026-07-01T00:10:00Z',
      cpu_usage: 41,
    },
  ],
} as any;

const metricChartData = [
  {
    date: '2026-07-01T00:00:00Z',
    cpu_usage: 42,
    memory_usage: 68,
  },
  {
    date: '2026-07-01T00:05:00Z',
    cpu_usage: 56,
    memory_usage: 71,
  },
  {
    date: '2026-07-01T00:10:00Z',
    cpu_usage: 38,
    memory_usage: 66,
  },
  {
    date: '2026-07-01T00:15:00Z',
    cpu_usage: 63,
    memory_usage: 73,
  },
  {
    date: '2026-07-01T00:20:00Z',
    cpu_usage: 48,
    memory_usage: 69,
  },
];

const metricChartMeta = {
  display_name: 'CPU Usage',
  display_description: 'Sample usage trend for monitor metric cards',
  color: '#165dff',
} as any;

const FamilyOverview = () => {
  const [displayMode, setDisplayMode] = React.useState<'dashboard' | 'metrics'>('dashboard');
  const [instanceValue, setInstanceValue] = React.useState('db-prod-01');

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Dashboard workspace shell"
          titleClassName="text-sm font-semibold"
          description="Shared dashboard headers, instance cards, detail panels, and stat cards define the core monitor reading experience across object dashboards."
        />

        <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <DashboardPageHeader
            title="MySQL / db-prod-01"
            displayMode={displayMode}
            onDisplayModeChange={setDisplayMode}
            timeDefaultValue={{
              selectValue: 0,
              rangePickerVaule: [dayjs().subtract(1, 'hour'), dayjs()],
            }}
            onTimeChange={() => undefined}
            onFrequenceChange={() => undefined}
            onRefresh={() => undefined}
            onBack={() => undefined}
            styles={headerStyles}
          />

          <DashboardInstanceCard
            instanceName="db-prod-01"
            metaItems={['MySQL 8.0.36', '10.0.0.21', '生产集群']}
            icon={<DatabaseOutlined />}
            selectorOptions={selectorOptions}
            selectorValue={instanceValue}
            onInstanceChange={setInstanceValue}
            styles={instanceCardStyles}
            timeSelectorProps={{
              timeDefaultValue: {
                selectValue: 15,
                rangePickerVaule: null,
              },
              onTimeChange: () => undefined,
              onFrequenceChange: () => undefined,
              onRefresh: () => undefined,
            }}
          />

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_320px]">
            <DetailPanel
              title="内存详情"
              subtitle="拆分展示主要内存去向"
              guide={[
                {
                  label: '内存详情',
                  detail: '用于拆分 RSS、缓存和可回收内存等细项，定位具体压力来源。',
                },
              ]}
              styles={detailPanelStyles}
            >
              <>
                <div className="flex items-center justify-between rounded-[12px] bg-[var(--color-fill-1)] px-4 py-3 text-[13px]">
                  <span>RSS</span>
                  <strong>1.82 GiB</strong>
                </div>
                <div className="flex items-center justify-between rounded-[12px] bg-[var(--color-fill-1)] px-4 py-3 text-[13px]">
                  <span>Cache</span>
                  <strong>612 MiB</strong>
                </div>
              </>
            </DetailPanel>

            <StatCard
              title="平均响应时间"
              value="482"
              unit="ms"
              color="#1677ff"
              icon={<DatabaseOutlined />}
              iconStyle={{ color: '#1677ff' }}
              compare={{
                direction: 'down',
                value: '12.4%',
              }}
              compareFavorableDirection="down"
              footer="近 15 分钟 · P95"
              trendData={trendData}
              styles={statCardStyles}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Integration and reporting semantics"
          titleClassName="text-sm font-semibold"
          description="Monitor surfaces also share a small badge language for access mode, reporting state, and alert type across asset and event views."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="flex flex-wrap items-center gap-3">
            <MonitorIntegrationAccessBadge mode="auto" />
            <MonitorIntegrationAccessBadge mode="manual" />
            <MonitorReportingStatusBadge status="normal" />
            <MonitorReportingStatusBadge status="online" />
            <MonitorReportingStatusBadge status="offline" />
            <MonitorReportingStatusBadge status="unavailable" />
            <MonitorReportingStatusBadge status="error" />
            <MonitorAlertTypeBadge alertType="alert" />
            <MonitorAlertTypeBadge alertType="no_data" />
            <MonitorAlertTypeBadge alertType="custom_type" label="Custom Type" />
            <MonitorAlertTypeBadge />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Metric rendering semantics"
          titleClassName="text-sm font-semibold"
          description="Metric cards, inline charts, and object icons form one governed monitor-language layer, so the metric view keeps one business contract instead of three isolated leaf stories."
        />

        <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Object icon states" titleClassName="text-sm font-medium" />
            <div className="mt-3 flex items-center gap-3">
              <MonitorObjectIcon icon="mm-mysql_Mysql" fallback={DEFAULT_OBJECT_ICON} size={20} />
              <MonitorObjectIcon icon={undefined} fallback={DEFAULT_OBJECT_ICON} size={20} />
              <span className="text-xs text-[var(--color-text-3)]">Fallback remains part of the same semantic icon contract.</span>
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Inline metric chart" titleClassName="text-sm font-medium" />
            <div className="mt-3 h-[320px] rounded-[12px] bg-[var(--color-bg-1)] p-3">
              <LineChart data={metricChartData as any} metric={metricChartMeta} unit="%" />
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Loaded metric card" titleClassName="text-sm font-medium" />
            <div className="mt-3">
              <MonitorLazyMetricItem
                item={metricCardItem}
                isLoading={false}
                isLoaded
                isCancelled={false}
                isInViewport
                onVisible={() => undefined}
                onSearchClick={() => undefined}
                onPolicyClick={() => undefined}
                onXRangeChange={() => undefined}
                onVisibilityChange={() => undefined}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Loading metric card" titleClassName="text-sm font-medium" />
            <div className="mt-3">
              <MonitorLazyMetricItem
                item={metricCardItem}
                isLoading
                isLoaded={false}
                isCancelled={false}
                isInViewport
                onVisible={() => undefined}
                onSearchClick={() => undefined}
                onPolicyClick={() => undefined}
                onXRangeChange={() => undefined}
                onVisibilityChange={() => undefined}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Integration config-state contract"
          titleClassName="text-sm font-semibold"
          description="Drawer and detail-route integration editors now share one governed business state for reported-only plugins, missing config payloads, and unsupported collect snippets."
        />

        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Reported only" titleClassName="text-sm font-medium" />
            <MonitorIntegrationConfigState variant="reportedOnly" description="This integration reports metrics but does not expose editable configuration." />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Missing config" titleClassName="text-sm font-medium" />
            <MonitorIntegrationConfigState variant="missingConfig" description="The current integration instance has no configuration content yet." />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Collect unsupported" titleClassName="text-sm font-medium" />
            <MonitorIntegrationConfigState variant="collectNotSupported" description="The selected collect template does not support snippet editing." />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Flow access guidance contract"
          titleClassName="text-sm font-semibold"
          description="Flow integration onboarding now uses the governed ordered-instruction shell for device-side export guidance instead of a page-local numbered list inside the access wizard."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="space-y-3">
            {[
              'Enable NetFlow export on the source device.',
              'Set the collector endpoint to 10.0.0.21:2055.',
              'Confirm the exporter source IP matches 10.0.0.12 before running access detection.',
              'Generate traffic, then return to the platform and detect access status.',
            ].map((item, index) => (
              <GuideStepPanel
                key={item}
                step={index + 1}
                title={item}
                spacing="flush"
              >
                {null}
              </GuideStepPanel>
            ))}
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Generated configuration snippets"
          titleClassName="text-sm font-semibold"
          description="Manual integration setup now renders generated configuration through the governed read-only snippet surface, while leaving editable configuration routes on their own dedicated editor contracts."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <CodeSnippet
            value={`hosts = ["10.0.0.21:9100"]\ninterval = "10s"\nlabels = { instance = "db-prod-01", region = "ap-southeast-1" }`}
            tone="inverse"
            copyable
            maxHeight={300}
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Editable collect-template editor"
          titleClassName="text-sm font-semibold"
          description="Monitor still keeps `CodeEditor` for true in-place editing flows, such as SNMP collect templates that users modify and save directly. This is intentionally distinct from generated read-only snippets."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <CodeEditor
            mode="toml"
            theme="monokai"
            name="monitor-collect-template-editor"
            width="100%"
            height="320px"
            value={`[[inputs.snmp]]
  agents = ["udp://10.0.0.21:161"]
  version = 2
  community = "public"
  interval = "30s"`}
            headerOptions={{ copy: true, fullscreen: true }}
            setOptions={{ showPrintMargin: false, useWorker: false }}
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Object workspace shell semantics"
          titleClassName="text-sm font-semibold"
          description="Object-tree navigation, search toolbar, and table workspace stay under one monitor business contract instead of drifting into separate leaf pages."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="h-[720px] overflow-hidden rounded-[16px] border border-[var(--color-border)] bg-[var(--color-bg-1)]">
            <MonitorObjectWorkspaceShell
              collapseStorageKey="storybook.monitor.objectWorkspace.family"
              sidebarHeader={(
                <PageHeaderShell
                  className="mb-[15px] px-2.5 pt-5"
                  title="Object types"
                  as="h3"
                  headerRowClassName="flex items-center justify-between gap-3"
                  titleRowClassName="flex items-center"
                  titleClassName="m-0 text-sm font-semibold text-[var(--color-text-1)]"
                  actions={(
                    <Button size="small" type="primary">
                      Add
                    </Button>
                  )}
                />
              )}
              sidebarContentClassName="h-full w-full overflow-hidden bg-[var(--color-bg-1)]"
              treeContainerClassName="flex-1 overflow-y-auto px-2.5 pb-2.5"
              treePanelProps={{
                data: objectTreeData,
                defaultSelectedKey: '3',
                onNodeSelect: () => undefined,
              }}
            >
              <div className="space-y-4">
                <Segmented options={['List', 'Topology']} value="List" />
                <SearchActionBar
                  spacing="flush"
                  searchProps={{
                    className: 'w-[320px]',
                    placeholder: 'Search instances',
                    allowClear: true,
                    enterButton: false,
                  }}
                  actions={<Button type="primary">Access</Button>}
                />
                <ManagementTableShell
                  panelClassName="bg-transparent p-0"
                  scroll={{ y: 420, x: 900 }}
                  columns={[
                    { title: 'Instance', dataIndex: 'name', key: 'name' },
                    { title: 'Status', dataIndex: 'status', key: 'status' },
                  ]}
                  dataSource={[
                    { id: '1', name: 'mysql-prod-01', status: 'Normal' },
                    { id: '2', name: 'mysql-prod-02', status: 'Warning' },
                  ]}
                  rowKey="id"
                />
              </div>
            </MonitorObjectWorkspaceShell>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Display fields modal design preview"
          titleClassName="text-sm font-semibold"
          description="The monitor-object display fields modal lives at app/monitor/(pages)/integration/object/displayFieldsModal.tsx. This section documents the visual contract as a design preview; future migration will replace the inline preview with the real component once a stable Storybook mock environment is available."
        />
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <DisplayFieldsModalPreview />
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/Monitor/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1240, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
