import type { Meta, StoryObj } from '@storybook/nextjs';
import React from 'react';
import { DndContext, PointerSensor, closestCenter, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, arrayMove, verticalListSortingStrategy } from '@dnd-kit/sortable';
import {
  AppstoreOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  LockOutlined,
  WarningFilled,
} from '@ant-design/icons';
import { Button, Menu, Tag } from 'antd';
import AutoFitMetricValue from '@/components/auto-fit-metric-value';
import CodeSnippet from '@/components/code-snippet';
import CustomTable from '@/components/custom-table';
import CopyableDetailList from '@/components/copyable-detail-list';
import DetailListPanel from '@/components/detail-list-panel';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import EventLevelIndicator from '@/app/alarm/components/event-level-indicator';
import EntityList from '@/components/entity-list';
import EventLevelTag from '@/app/alarm/components/event-level-tag';
import EventStatusTag from '@/app/alarm/components/event-status-tag';
import ExecutionStatusBadge from '@/components/execution-status-badge';
import HttpEndpointDisplay from '@/components/http-endpoint-display';
import HttpMethodBadge from '@/components/http-method-badge';
import MarkdownRenderer from '@/components/markdown';
import RatioProgressCell from '@/components/ratio-progress-cell';
import SectionHeader from '@/components/section-header';
import SecretValueDisplay from '@/components/secret-value-display';
import SemanticBadge from '@/components/semantic-badge';
import SourceOriginBadge from '@/components/source-origin-badge';
import SortableItem from '@/components/sortable-item';
import StatusBadgeShell from '@/components/status-badge-shell';
import StructuredDataPreview from '@/components/structured-data-preview';
import SummaryMetricCard from '@/components/summary-metric-card';
import TagCapsuleGroup from '@/components/tag-capsule-group';
import UserAvatar from '@/components/user-avatar';
import VersionBadge from '@/components/version-badge';

interface ExampleItem {
  id: string;
  name: string;
  description: string;
  icon: string;
  tagList?: string[];
  is_build_in?: boolean;
}

const entityData: ExampleItem[] = [
  {
    id: '1',
    name: 'MySQL Primary',
    description: 'Production transactional database cluster.',
    icon: 'mysql',
    tagList: ['database', 'prod'],
    is_build_in: true,
  },
  {
    id: '2',
    name: 'Kubernetes Collector',
    description: 'Collects cluster metrics, events, and topology signals.',
    icon: 'kubernetes',
    tagList: ['k8s', 'infra'],
    is_build_in: false,
  },
  {
    id: '3',
    name: 'Alert Routing Policy',
    description: 'Shared policy pack for event escalation and suppression.',
    icon: 'gaojing',
    tagList: ['policy'],
  },
];

const governedEntityData: ExampleItem[] = [
  {
    id: '4',
    name: 'Incident Skill Package',
    description: 'Reusable knowledge package for guided incident triage.',
    icon: 'zhishiku',
    tagList: ['协作', '搜索'],
    is_build_in: true,
  },
  {
    id: '5',
    name: 'Tool Marketplace Entry',
    description: 'Self-built automation catalog entry with external ownership.',
    icon: 'tool',
    tagList: ['运维', '其他'],
    is_build_in: false,
  },
];

const FamilyOverview = () => {
  const [draggableRows, setDraggableRows] = React.useState([
    { key: '1', name: 'Hostname', type: 'string' },
    { key: '2', name: 'IP Address', type: 'string' },
    { key: '3', name: 'Environment', type: 'enum' },
  ]);
  const [lastMove, setLastMove] = React.useState('No drag yet');
  const [sortableItems, setSortableItems] = React.useState([
    { id: 'primary', label: 'Primary access key', note: 'Shared secret used by default automation.' },
    { id: 'fallback', label: 'Fallback access key', note: 'Secondary credential for failover access.' },
    { id: 'readonly', label: 'Readonly credential', note: 'Inspection-only credential kept at the bottom of the list.' },
  ]);
  const [lastListMove, setLastListMove] = React.useState('No drag yet');
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
  );

  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Dense operational table" titleClassName="text-sm font-semibold" />
        <CustomTable
          rowKey="key"
          pagination={false}
          dataSource={[
            {
              key: '1',
              name: 'CPU threshold reached on compute-cluster-a / node-001',
              severity: 'High',
              status: 'Open',
              owner: 'alice',
              score: '91.3%',
            },
            {
              key: '2',
              name: 'Disk warning on storage cluster / shard-02',
              severity: 'Medium',
              status: 'Closed',
              owner: 'bob',
              score: '62.4%',
            },
          ]}
          columns={[
            {
              title: 'Name',
              dataIndex: 'name',
              key: 'name',
              render: (value: string) => (
                <EllipsisWithTooltip
                  text={value}
                  className="block max-w-[320px] overflow-hidden text-ellipsis whitespace-nowrap text-sm"
                />
              ),
            },
            {
              title: 'Severity',
              dataIndex: 'severity',
              key: 'severity',
              render: (value: string) => (
                <EventLevelTag
                  label={value}
                  color={value === 'High' ? '#f97316' : '#facc15'}
                />
              ),
            },
            {
              title: 'Status',
              dataIndex: 'status',
              key: 'status',
              render: (value: string) => (
                <EventStatusTag label={value} active={value === 'Open'} />
              ),
            },
            {
              title: 'Owner',
              dataIndex: 'owner',
              key: 'owner',
              render: (value: string) => <UserAvatar userName={value} />,
            },
            {
              title: 'Health',
              dataIndex: 'score',
              key: 'score',
              render: (value: string) => (
                <div className="w-[120px]">
                  <RatioProgressCell
                    value={value}
                    strokeColor={value === '91.3%' ? '#f5222d' : undefined}
                  />
                </div>
              ),
            },
          ]}
        />

        <div className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader
              className="mb-3"
              title="Default completion ratio"
              titleClassName="text-sm font-medium"
            />
            <RatioProgressCell value="62.4%" />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader
              className="mb-3"
              title="Risk-highlighted ratio"
              titleClassName="text-sm font-medium"
            />
            <RatioProgressCell value="91.3%" strokeColor="#f5222d" />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader
              className="mb-3"
              title="Empty ratio fallback"
              titleClassName="text-sm font-medium"
            />
            <RatioProgressCell value={null} />
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader
              className="mb-3"
              title="Row selection with pagination"
              titleClassName="text-sm font-medium"
              description="Shared data tables keep selection, status-tag rendering, and paginated footers aligned across monitor, CMDB, and system-manager list pages."
            />
            <CustomTable
              rowSelection={{
                selectedRowKeys: ['1', '3'],
                onChange: () => undefined,
              }}
              pagination={{
                current: 1,
                pageSize: 5,
                total: 12,
              }}
              dataSource={[
                { key: '1', name: 'API Gateway', status: 'Healthy', owner: 'Platform' },
                { key: '2', name: 'Billing Worker', status: 'Warning', owner: 'Finance' },
                { key: '3', name: 'Search Indexer', status: 'Healthy', owner: 'Infra' },
              ]}
              columns={[
                { title: 'Name', dataIndex: 'name', key: 'name' },
                {
                  title: 'Status',
                  dataIndex: 'status',
                  key: 'status',
                  render: (value: string) => (
                    <Tag color={value === 'Healthy' ? 'green' : 'gold'}>{value}</Tag>
                  ),
                },
                { title: 'Owner', dataIndex: 'owner', key: 'owner' },
              ]}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader
              className="mb-3"
              title="Field setting"
              titleClassName="text-sm font-medium"
              description="The same shared table contract also owns column-visibility governance without requiring app-local settings drawers."
            />
            <CustomTable
              pagination={false}
              dataSource={[
                { key: '1', name: 'Node-01', ip: '10.0.0.8', region: 'ap-south-1' },
                { key: '2', name: 'Node-02', ip: '10.0.0.9', region: 'eu-west-1' },
              ]}
              columns={[
                { title: 'Name', dataIndex: 'name', key: 'name' },
                { title: 'IP', dataIndex: 'ip', key: 'ip' },
                { title: 'Region', dataIndex: 'region', key: 'region' },
              ]}
              fieldSetting={{
                showSetting: true,
                displayFieldKeys: ['name', 'ip'],
                choosableFields: [
                  { title: 'Name', key: 'name', dataIndex: 'name' },
                  { title: 'IP', key: 'ip', dataIndex: 'ip' },
                  { title: 'Region', key: 'region', dataIndex: 'region' },
                ],
                groupFields: [
                  {
                    title: 'Core',
                    key: 'core',
                    child: [
                      { title: 'Name', key: 'name', dataIndex: 'name' },
                      { title: 'IP', key: 'ip', dataIndex: 'ip' },
                    ],
                  },
                  {
                    title: 'Topology',
                    key: 'topology',
                    child: [{ title: 'Region', key: 'region', dataIndex: 'region' }],
                  },
                ],
              }}
              onSelectFields={() => undefined}
            />
          </div>
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
          <SectionHeader
            className="mb-3"
            title="Row drag ordering"
            titleClassName="text-sm font-medium"
            description="Drag-reorder behavior stays on the shared table primitive so workspace-specific ordering pages do not fork table layout and handle wiring."
          />
          <div className="space-y-3">
            <CustomTable
              rowKey="key"
              rowDraggable
              pagination={false}
              dataSource={draggableRows}
              columns={[
                { title: 'Field', dataIndex: 'name', key: 'name' },
                { title: 'Type', dataIndex: 'type', key: 'type' },
              ]}
              onRowDragEnd={(nextRows, sourceIndex, targetIndex) => {
                setDraggableRows((nextRows || []) as typeof draggableRows);
                setLastMove(`Moved row ${sourceIndex} to ${targetIndex}`);
              }}
            />
            <div className="text-xs text-[var(--color-text-3)]">{lastMove}</div>
          </div>
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
          <SectionHeader
            className="mb-3"
            title="Handle-only list ordering"
            titleClassName="text-sm font-medium"
            description="Thin sortable list wiring stays governed with the rest of shared data-display ordering behavior, so CMDB-style editors do not need a separate Storybook root for the same drag contract."
          />
          <div className="space-y-3">
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={({ active, over }) => {
                if (!over || active.id === over.id) return;
                const oldIndex = sortableItems.findIndex((item) => item.id === active.id);
                const newIndex = sortableItems.findIndex((item) => item.id === over.id);
                if (oldIndex === -1 || newIndex === -1) return;
                setSortableItems((current) => arrayMove(current, oldIndex, newIndex));
                setLastListMove(`Moved item ${oldIndex} to ${newIndex}`);
              }}
            >
              <SortableContext
                items={sortableItems.map((item) => item.id)}
                strategy={verticalListSortingStrategy}
              >
                <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {sortableItems.map((item, index) => (
                    <SortableItem key={item.id} id={item.id} index={index}>
                      <span className="cursor-grab px-2 py-3 text-[var(--color-text-3)]">::</span>
                      <div className="flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] px-3 py-3">
                        <div className="text-sm font-medium text-[var(--color-text-1)]">{item.label}</div>
                        <div className="mt-1 text-xs text-[var(--color-text-3)]">{item.note}</div>
                      </div>
                    </SortableItem>
                  ))}
                </ul>
              </SortableContext>
            </DndContext>
            <div className="text-xs text-[var(--color-text-3)]">{lastListMove}</div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Metric display contract" titleClassName="text-sm font-semibold" />
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-3">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader
                className="mb-3"
                title="Baseline metric value"
                titleClassName="text-sm font-medium"
                description="Shared auto-fit values keep numeric emphasis stable for KPI widgets, cards, and chart-derived singles."
              />
              <div className="h-[140px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
                <AutoFitMetricValue
                  main="14,495"
                  unit="ms"
                  color="var(--color-primary)"
                  unitColor="color-mix(in srgb, var(--color-primary) 78%, white)"
                  valueClassName="font-semibold"
                  unitClassName="font-medium"
                  unitScale={0.48}
                  align="baseline"
                  resolveFontSize={({ width, height }) =>
                    Math.min(Math.max(width / 5, 24), Math.max(height / 2.8, 24), 56)
                  }
                />
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader
                className="mb-3"
                title="Centered number"
                titleClassName="text-sm font-medium"
                description="Number-only displays keep centered emphasis without requiring business-local resize math."
              />
              <div className="h-[140px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
                <AutoFitMetricValue
                  main="18240"
                  color="var(--color-text-1)"
                  align="end"
                  valueClassName="flex w-full justify-center font-semibold"
                  resolveFontSize={({ width, height }) =>
                    Math.min(Math.max((width - 24) / 4.4, 20), Math.max(height / 1.5, 20), 96)
                  }
                />
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader
                className="mb-3"
                title="Long label fallback"
                titleClassName="text-sm font-medium"
                description="The same primitive also owns oversized string fallback when a metric surface shows a status-like value."
              />
              <div className="h-[140px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
                <AutoFitMetricValue
                  main="ConnectionTimeout"
                  color="#fd666d"
                  textShadow="0 0 18px rgba(253, 102, 109, 0.18)"
                  valueClassName="font-semibold"
                  resolveFontSize={({ width, height }) =>
                    Math.min(Math.max(width / 8.5, 18), Math.max(height / 3.2, 18), 40)
                  }
                />
              </div>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SummaryMetricCard
                icon={<CheckCircleOutlined />}
                iconBackground="#E8FFEA"
                iconColor="#00B42A"
                label="今日事件"
                value="18,240"
                unit="条"
                subtitle="↑ 12.4%"
                subtitleColor="#F53F3F"
                className="p-[18px_20px]"
                iconClassName="h-[46px] w-[46px]"
              />
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SummaryMetricCard
                icon={<ClockCircleOutlined />}
                iconBackground="#E8F0FF"
                iconColor="#155AEF"
                label="最近同步"
                value="2 小时前"
                className="min-h-[78px] rounded-md border-[#d6deea] bg-white px-3 py-3 transition-colors hover:border-[#c5d0df] xl:px-4"
                iconClassName="h-9 w-9 rounded-[10px] text-[16px] xl:h-10 xl:w-10 xl:text-[18px]"
                labelClassName="font-medium text-[#5f6f86]"
                valueColor="#0f172a"
                valueClassName="tracking-tight text-[24px]"
                minFontSize={20}
                maxFontSize={28}
              />
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SummaryMetricCard
                icon={<AppstoreOutlined />}
                iconBackground="#E8F0FF"
                iconColor="#155AEF"
                label="模型覆盖数"
                value="99.21"
                unit="%"
                className="p-5"
                iconClassName="h-10 w-10 rounded-[12px] text-[18px]"
                valueClassName="text-[32px]"
              />
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SummaryMetricCard
                label="已归属事故"
                value="INC-2026-0012"
                subtitle="当前上下文事故"
                className="p-4 shadow-sm"
                valueClassName="text-[18px] font-medium"
                subtitleClassName="text-sm"
                minFontSize={16}
                maxFontSize={20}
              />
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SummaryMetricCard
                layout="vertical"
                icon={<CheckCircleOutlined />}
                iconBackground="rgba(25,184,122,.12)"
                iconColor="#19b87a"
                label="成功率"
                headerExtra={(
                  <span
                    style={{
                      background: 'rgba(238,241,246,1)',
                      color: 'var(--color-text-3)',
                      fontSize: 11,
                      padding: '2px 8px',
                      borderRadius: 6,
                    }}
                  >
                    最近 7 天
                  </span>
                )}
                value="98.4"
                unit="%"
                valueColor="#19b87a"
                valueAside={<span style={{ color: '#0e8a59', fontSize: 12, fontWeight: 600 }}>▲ 2.1%</span>}
                subtitle="较上周期"
                footer={<div style={{ height: 8, borderRadius: 999, background: 'rgba(25,184,122,.12)' }} />}
                className="p-4"
                headerSpacing="spacious"
                iconClassName="h-8 w-8 rounded-[9px] text-[18px]"
                valueClassName="text-[30px] tracking-tight"
                footerClassName="mt-auto pt-4"
                minFontSize={24}
                maxFontSize={30}
              />
            </div>

            <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SummaryMetricCard
                layout="vertical"
                framed={false}
                label="累计事件"
                value="12,480"
                subtitle="事件列表加载后会持续更新该统计。"
                className="min-h-[96px] py-2"
                labelClassName="text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--color-text-3)]"
                valueClassName="text-[22px] font-semibold leading-[28px] text-[var(--color-text-1)]"
                subtitleClassName="max-w-[260px] text-[12px] leading-5 text-[var(--color-text-2)]"
                minFontSize={18}
                maxFontSize={22}
              />

              <SummaryMetricCard
                layout="vertical"
                framed={false}
                label="新增数据"
                value={182}
                valueColor="#2563eb"
                subtitle="写入失败 3 条"
                subtitleColor="#dc2626"
                className="rounded-md border border-blue-200 bg-blue-50 px-4 py-3"
                headerSpacing="compact"
                labelClassName="text-xs text-[var(--color-text-3)]"
                valueClassName="text-[28px] font-bold"
                subtitleClassName="text-xs font-medium"
                minFontSize={22}
                maxFontSize={28}
              />
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_360px]">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Detail rows and payload previews" titleClassName="text-sm font-semibold" />
          <div className="space-y-4">
            <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)]">
              <CopyableDetailList
                labelWidthClassName="w-32"
                items={[
                  {
                    label: 'Endpoint',
                    displayValue: (
                      <HttpEndpointDisplay
                        method="POST"
                        endpoint="https://api.example.com/v1/events"
                        badgeClassName="text-[11px] font-semibold"
                        endpointClassName="whitespace-normal break-all text-xs"
                      />
                    ),
                    copyable: false,
                  },
                  {
                    label: 'Secret',
                    displayValue: <SecretValueDisplay value="bk-lite-secret-token" />,
                    copyable: false,
                  },
                  {
                    label: 'Payload',
                    displayValue: (
                      <StructuredDataPreview
                        value={{
                          event_id: 'evt-2026-06-30',
                          status: 'warning',
                          labels: ['monitor', 'storybook'],
                        }}
                        className="!bg-transparent !p-0 !text-xs"
                        maxHeight="9rem"
                      />
                    ),
                    copyable: false,
                  },
                ]}
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)]">
                <SectionHeader
                  className="px-3 pt-3"
                  title="Plain detail rows"
                  titleClassName="text-sm font-medium"
                  description="Baseline key/value rows keep the same shared copy affordance without requiring app-local shells."
                />
                <CopyableDetailList
                  items={[
                    { label: 'Name', value: 'bk-lite-knowledge-node' },
                    { label: 'Summary', value: 'Cross-app component governance detail surface' },
                    { label: 'UUID', value: 'e8ab6a2a-0c59-4fb0-bb06-30f424d5c0fb' },
                  ]}
                />
              </div>

              <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)]">
                <SectionHeader
                  className="px-3 pt-3"
                  title="Empty detail values"
                  titleClassName="text-sm font-medium"
                  description="The same shared row contract owns empty-value fallback rendering across asset, relation, and integration details."
                />
                <CopyableDetailList
                  items={[
                    { label: 'Fact', value: '' },
                    { label: 'Relation Type', value: 'depends_on' },
                    { label: 'Source Name', value: null },
                    { label: 'Target Name', value: 'collector-service' },
                  ]}
                />
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Framed detail panel"
                  titleClassName="text-sm font-medium"
                  description="Alarm guides, CMDB task details, and monitor integration access steps reuse the same framed detail-panel wrapper instead of re-declaring local shells."
                />
                <DetailListPanel
                  labelWidthClassName="w-32"
                  items={[
                    { label: 'Name', value: 'collector-a' },
                    { label: 'Cluster', value: 'prod-hz-1' },
                    { label: 'Endpoint', value: 'https://api.example.com/v1/events' },
                  ]}
                />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Guide-style detail panel"
                  titleClassName="text-sm font-medium"
                  description="The same panel wrapper also governs richer guide payloads with structured previews and non-copyable values."
                />
                <DetailListPanel
                  className="overflow-hidden rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)]"
                  labelWidthClassName="w-40"
                  items={[
                    {
                      label: 'Webhook',
                      value: 'https://alarm.example.com/api/receive',
                      displayValue: (
                        <div className="space-y-1">
                          <div className="font-medium text-gray-900">
                            POST https://alarm.example.com/api/receive
                          </div>
                          <div className="text-gray-500">
                            Shared data-display shell for copyable integration details.
                          </div>
                        </div>
                      ),
                    },
                    {
                      label: 'Headers',
                      copyable: false,
                      displayValue: (
                        <StructuredDataPreview
                          value={{ SECRET: '******', 'Content-Type': 'application/json' }}
                          className="!bg-transparent !p-0 !text-xs"
                          maxHeight="10rem"
                        />
                      ),
                    },
                  ]}
                />
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Long endpoint wrapping"
                  titleClassName="text-sm font-medium"
                  description="The shared endpoint surface also owns long-path wrapping behavior for model-serving and custom integration URLs."
                />
                <HttpEndpointDisplay
                  method="POST"
                  endpoint="https://bk-lite.example/api/mlops/predict/timeseries_predict/serving-1234567890-long-endpoint"
                  endpointClassName="whitespace-normal break-all text-xs"
                  badgeClassName="text-[11px] font-semibold"
                />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Empty endpoint"
                  titleClassName="text-sm font-medium"
                  description="When no endpoint is available yet, the same shared display primitive owns the empty fallback contract."
                />
                <HttpEndpointDisplay
                  method="POST"
                  endpoint=""
                  endpointClassName="whitespace-normal break-all text-xs"
                  badgeClassName="text-[11px] font-semibold"
                />
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Multiline payload preview"
                  titleClassName="text-sm font-medium"
                  description="String payloads keep line breaks and wrapping without leaving the shared preview contract."
                />
                <StructuredDataPreview
                  value={'Step 1: Fetch signal\nStep 2: Normalize payload\nStep 3: Queue downstream task'}
                  className="!text-xs"
                  maxHeight="10rem"
                />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Empty payload preview"
                  titleClassName="text-sm font-medium"
                  description="The same shared preview owns the empty-state fallback when upstream payloads are absent."
                />
                <StructuredDataPreview
                  value={undefined}
                  empty="No preview available"
                />
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Visible secret value"
                  titleClassName="text-sm font-medium"
                  description="Shared secret rows can reveal the raw value when the surrounding workflow explicitly asks for it."
                />
                <SecretValueDisplay
                  value="bk_secret_live_123456"
                  masked={false}
                />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Secret placeholder"
                  titleClassName="text-sm font-medium"
                  description="When a team or credential is not chosen yet, the same secret primitive owns the placeholder contract."
                />
                <SecretValueDisplay
                  value=""
                  placeholder={<span className="text-[var(--color-text-3)]">&lt;Select a team&gt;</span>}
                />
              </div>
            </div>

            <p className="text-xs leading-5 text-[var(--color-text-3)]">
              Shared detail surfaces now converge on the same endpoint, secret, structured payload,
              and copy-row contracts instead of app-local key/value shells.
            </p>
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Entity catalog surface" titleClassName="text-sm font-semibold" />
          <div className="space-y-4">
            <EntityList
              data={entityData}
              loading={false}
              search={true}
              filter={true}
              filterOptions={[
                { label: 'Database', value: 'database' },
                { label: 'Infra', value: 'infra' },
                { label: 'Policy', value: 'policy' },
              ]}
              toolbarPrefix={<SectionHeader spacing="flush" title="Shared catalog" titleClassName="text-sm font-medium" />}
              operateSection={<Button type="primary">Create entity</Button>}
              onSearch={() => undefined}
              changeFilter={() => undefined}
              menuActions={(item: ExampleItem) => (
                <Menu>
                  <Menu.Item key="edit">Edit {item.name}</Menu.Item>
                  <Menu.Item key="delete">Delete {item.name}</Menu.Item>
                </Menu>
              )}
              onCardClick={() => undefined}
              openModal={() => undefined}
            />

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Loading catalog"
                  titleClassName="text-sm font-medium"
                  description="The shared catalog shell also owns loading-state framing while the next batch of entity cards is being prepared."
                />
                <EntityList
                  data={[]}
                  loading
                  onSearch={() => undefined}
                  openModal={() => undefined}
                />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Empty catalog"
                  titleClassName="text-sm font-medium"
                  description="When no entities match the current workspace or filter, the same shared catalog surface keeps the empty-state contract aligned."
                />
                <EntityList
                  data={[]}
                  loading={false}
                  search
                  onSearch={() => undefined}
                  openModal={() => undefined}
                />
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Semantic tag colors and hidden builtin badge"
                  titleClassName="text-sm font-medium"
                  description="OpsPilot catalog pages reuse EntityList with semantic tag colors while hiding the builtin badge when source ownership is communicated elsewhere."
                />
                <EntityList
                  data={governedEntityData}
                  loading={false}
                  search={false}
                  filter={false}
                  showBuiltinTag={false}
                  infoText="Managed by AI Ops"
                  onSearch={() => undefined}
                  onCardClick={() => undefined}
                />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Button-style single action"
                  titleClassName="text-sm font-medium"
                  description="Knowledge and tool management flows can switch the single action to a button-style affordance without forking the shared catalog card shell."
                />
                <EntityList
                  data={governedEntityData}
                  loading={false}
                  search={false}
                  filter={false}
                  showBuiltinTag={false}
                  singleActionType="button"
                  singleAction={(item: ExampleItem) => ({
                    text: `Configure ${item.name}`,
                    onClick: () => undefined,
                  })}
                  onSearch={() => undefined}
                  onCardClick={() => undefined}
                />
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Default avatar"
                  titleClassName="text-sm font-medium"
                />
                <UserAvatar userName="admin" />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Long-name avatar"
                  titleClassName="text-sm font-medium"
                />
                <UserAvatar userName="alexander.hamilton" />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Small avatar"
                  titleClassName="text-sm font-medium"
                />
                <UserAvatar userName="test" size="small" />
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Inline display semantics" titleClassName="text-sm font-semibold" />
          <div className="space-y-4">
            <div className="grid gap-4 lg:grid-cols-3">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Long ellipsis text"
                  titleClassName="text-sm font-medium"
                />
                <EllipsisWithTooltip
                  text="这是一段非常非常长的文本内容，它可能会超出容器的宽度显示，当超出时应该显示省略号并在悬停时展示完整内容。"
                  className="block whitespace-nowrap overflow-hidden text-ellipsis text-sm"
                />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Short text"
                  titleClassName="text-sm font-medium"
                />
                <EllipsisWithTooltip
                  text="短文本"
                  className="block whitespace-nowrap overflow-hidden text-ellipsis text-sm"
                />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Custom ellipsis style"
                  titleClassName="text-sm font-medium"
                />
                <EllipsisWithTooltip
                  text="自定义样式的文本"
                  className="block text-lg font-bold whitespace-nowrap overflow-hidden text-ellipsis"
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <EventLevelIndicator label="Critical" color="#F43B2C" />
              <EventLevelIndicator label="Warning" color="#FAAD14" />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <HttpMethodBadge method="GET" />
              <HttpMethodBadge method="POST" />
              <HttpMethodBadge method="PUT" />
              <HttpMethodBadge method="DELETE" />
              <HttpMethodBadge method="PATCH" />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <ExecutionStatusBadge status="pending" label="Pending" />
              <ExecutionStatusBadge status="running" label="Running" />
              <ExecutionStatusBadge status="completed" label="Completed" />
              <ExecutionStatusBadge status="failed" label="Failed" />
              <ExecutionStatusBadge status="published" label="Published" />
              <ExecutionStatusBadge status="interrupt_requested" label="Interrupting" />
              <ExecutionStatusBadge status="terminating" label="Terminating" />
              <ExecutionStatusBadge status="unknown" label="Unknown" />
              <ExecutionStatusBadge status="not_found" label="Stopped" />
              <ExecutionStatusBadge status="archived" label="Archived" />
              <ExecutionStatusBadge status="cancelled" label="Cancelled" />
              <ExecutionStatusBadge status="interrupted" label="Interrupted" />
              <ExecutionStatusBadge status="killed" label="Killed" />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <EventLevelTag
                label="Critical"
                color="#F43B2C"
                withIcon
              />
              <SemanticBadge
                label="INFO"
                textColor="#1677ff"
                backgroundColor="rgba(22, 119, 255, 0.12)"
              />
              <SemanticBadge
                label="Permission Changed"
                textColor="#5a6d7f"
                backgroundColor="rgba(90, 109, 127, 0.12)"
                minWidth={60}
                centered={true}
              />
              <SemanticBadge
                label="500"
                textColor="#f5222d"
                backgroundColor="rgba(245, 34, 45, 0.12)"
                minWidth={44}
                centered={true}
              />
              <SemanticBadge
                label="Success"
                textColor="var(--color-success)"
                backgroundColor="color-mix(in srgb, var(--color-success) 12%, transparent)"
              />
              <SemanticBadge
                label="Failed"
                textColor="var(--color-error)"
                backgroundColor="color-mix(in srgb, var(--color-error) 12%, transparent)"
              />
              <SemanticBadge
                label="Modified 8"
                textColor="var(--color-warning)"
                backgroundColor="color-mix(in srgb, var(--color-warning) 12%, transparent)"
              />
              <SemanticBadge
                label="Total: 24"
                textColor="var(--color-text-2)"
                backgroundColor="color-mix(in srgb, var(--color-fill-5) 32%, transparent)"
              />
              <SemanticBadge
                label="NO"
                textColor="#2f54eb"
                backgroundColor="rgba(47, 84, 235, 0.12)"
              />
              <SemanticBadge
                label="24"
                textColor="var(--color-primary)"
                backgroundColor="color-mix(in srgb, var(--color-primary) 12%, transparent)"
              />
              <SemanticBadge
                label={(
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <LockOutlined />
                    <span>No Auth</span>
                  </span>
                )}
                textColor="var(--color-warning)"
                backgroundColor="color-mix(in srgb, var(--color-warning) 12%, transparent)"
              />
              <Tag color="gold">Warning</Tag>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <EventLevelTag
                label="Warning"
                color="#FAAD14"
                withIcon={false}
              />
              <EventLevelTag
                label="Major"
                color="#1677ff"
                icon={<WarningFilled />}
              />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <StatusBadgeShell
                label="Completed"
                palette={{
                  textColor: 'var(--color-success)',
                  backgroundColor: 'color-mix(in srgb, var(--color-success) 12%, transparent)',
                }}
              />
              <StatusBadgeShell
                label="Pending Review"
                minWidth={120}
                palette={{
                  textColor: 'var(--color-warning)',
                  backgroundColor: 'color-mix(in srgb, var(--color-warning) 12%, transparent)',
                }}
              />
              <StatusBadgeShell
                label="Unknown"
                centered
                minWidth={72}
                palette={{
                  textColor: 'var(--color-text-3)',
                  backgroundColor: 'color-mix(in srgb, var(--color-text-4) 18%, transparent)',
                }}
              />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <SourceOriginBadge kind="builtin" />
              <SourceOriginBadge kind="external" />
              <SourceOriginBadge kind="custom" />
              <SourceOriginBadge kind="imported" label="Imported" />
              <SourceOriginBadge kind="builtin" mode="inline" parenthesized />
              <SourceOriginBadge kind="builtin" label="Built-in Model" />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <VersionBadge value="v2.3.1" />
              <VersionBadge value="" />
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
              <MarkdownRenderer
                content={`### Display Notes\n- Shared display primitives keep dense UI readable.\n- Tables, badges, and inline states should speak the same visual language across apps.`}
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Tag capsules"
                  titleClassName="text-sm font-medium"
                />
                <TagCapsuleGroup value={['Platform', 'Operations', 'Database']} />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Compact tag capsules"
                  titleClassName="text-sm font-medium"
                />
                <TagCapsuleGroup value={['Platform', 'Operations', 'Database']} compact />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Overflow tag capsules"
                  titleClassName="text-sm font-medium"
                />
                <TagCapsuleGroup
                  value={['Platform', 'Operations', 'Database', 'Security', 'Middleware']}
                  maxVisible={2}
                />
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Snippet default"
                  titleClassName="text-sm font-medium"
                />
                <CodeSnippet
                  value={`curl -X POST "https://bk-lite.example/api/v1/collect" \\
  -H "Authorization: Bearer <token>" \\
  -H "Content-Type: application/json" \\
  -d '{"status":"ok"}'`}
                />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Copyable snippet"
                  titleClassName="text-sm font-medium"
                />
                <CodeSnippet
                  copyable
                  value={`curl -X POST "https://bk-lite.example/api/v1/collect" \\
  -H "Authorization: Bearer <token>" \\
  -H "Content-Type: application/json" \\
  -d '{"status":"ok"}'`}
                />
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
                <SectionHeader
                  className="mb-3"
                  title="Inverse snippet"
                  titleClassName="text-sm font-medium"
                />
                <CodeSnippet
                  tone="inverse"
                  copyable
                  value={`curl -X POST "https://bk-lite.example/api/v1/collect" \\
  -H "Authorization: Bearer <token>" \\
  -H "Content-Type: application/json" \\
  -d '{"status":"ok"}'`}
                />
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
              <SectionHeader
                className="mb-3"
                title="Empty markdown"
                titleClassName="text-sm font-medium"
              />
              <MarkdownRenderer content="" />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

const meta = {
  title: 'Framework/DataDisplay/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1180, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
