import type { Meta, StoryObj } from '@storybook/react';
import React from 'react';
import { Button, Form, Select, Tag, Tooltip } from 'antd';
import EventAlertWorkspaceShell from '@/components/event-alert-workspace-shell';
import EventAlertInformationSummary from '@/components/event-alert-information-summary';
import EventCloseAction from '@/components/event-close-action';
import EventDetailDrawer from '@/components/event-detail-drawer';
import EventDetailHeader from '@/components/event-detail-drawer/header';
import EventTimelinePanel from '@/components/event-detail-drawer/timeline-panel';
import EventNotificationForm from '@/components/event-notification-form';
import { createMonitorEventNotificationPreset } from '@/components/event-notification-form/presets';
import EventStrategyPanel from '@/components/event-strategy-panel';
import EventStrategyIdentityFields from '@/components/event-strategy-identity-fields';
import EventLevelIndicator from '@/components/event-level-indicator';
import FilterToolbar from '@/components/filter-toolbar';
import Icon from '@/components/icon';
import SectionHeader from '@/components/section-header';
import StackedBarChart from '@/components/stacked-bar-chart';
import TimeSelector from '@/components/time-selector';
import {
  eventNotificationChannels as channels,
  eventNotificationStoryT as t,
  eventNotificationUsers as users,
} from './event-notification-form.fixtures';

interface DemoEvent {
  id: string;
  event_time: string;
  content: string;
}

const demoEvents: DemoEvent[] = [
  {
    id: '1',
    event_time: '2026-06-24T09:00:00.000Z',
    content: 'Threshold exceeded on node-a',
  },
  {
    id: '2',
    event_time: '2026-06-24T10:00:00.000Z',
    content: 'Threshold exceeded on node-b',
  },
];

const eventAlertChartData = [
  { time: '10:00', critical: 1, warning: 2, error: 0 },
  { time: '10:05', critical: 0, warning: 3, error: 1 },
];

const eventAlertTableData = [
  { id: '1', level: 'Critical', name: 'CPU Alert', state: 'Open' },
  { id: '2', level: 'Warning', name: 'Disk Alert', state: 'Closed' },
];

const eventAlertTabs = [
  { key: 'activeAlarms', label: 'Active alarms' },
  { key: 'closedAlarms', label: 'Closed alarms' },
];

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Event list actions" titleClassName="text-sm font-semibold" />
        <div className="flex flex-wrap gap-3">
          <EventCloseAction
            scope="monitor.events"
            label="Close"
            onConfirm={async () => undefined}
          />
          <EventCloseAction
            scope="log.event"
            label="Close alert"
            onConfirm={async () => undefined}
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Event detail shell" titleClassName="text-sm font-semibold" />
        <div className="space-y-4">
          <div style={{ height: 560 }}>
            <EventDetailDrawer<DemoEvent>
              visible={true}
              title="Event detail"
              headerTitle="CPU utilization threshold alert"
              levelLabel="High"
              levelColor="#ff4d4f"
              activeTab="information"
              tabs={[
                { key: 'information', label: 'Information' },
                { key: 'timeline', label: 'Timeline' },
              ]}
              onTabChange={() => undefined}
              onClose={() => undefined}
              closeLabel="Cancel"
              metaItems={[
                { key: 'time', label: 'Time', value: '2026-06-24 17:00:00' },
                {
                  key: 'state',
                  label: 'State',
                  value: <Tag color="blue">Open</Tag>,
                },
              ]}
              informationContent={(
                <div style={{ paddingBottom: 24 }}>
                  <p style={{ marginBottom: 12 }}>
                    Shared drawer shell for monitor and log event detail flows.
                  </p>
                  <p style={{ margin: 0 }}>
                    Domain-specific information blocks stay outside the shared layer.
                  </p>
                </div>
              )}
              events={demoEvents}
              renderTimelineContent={(item) => item.content}
            />
          </div>

          <div style={{ height: 560 }}>
            <EventDetailDrawer<DemoEvent>
              visible={true}
              title="Event detail"
              headerTitle="CPU utilization threshold alert"
              levelLabel="High"
              levelColor="#ff4d4f"
              activeTab="timeline"
              tabs={[
                { key: 'information', label: 'Information' },
                { key: 'timeline', label: 'Timeline' },
              ]}
              onTabChange={() => undefined}
              onClose={() => undefined}
              closeLabel="Cancel"
              metaItems={[
                { key: 'time', label: 'Time', value: '2026-06-24 17:00:00' },
                {
                  key: 'state',
                  label: 'State',
                  value: <Tag color="blue">Open</Tag>,
                },
              ]}
              informationContent={(
                <div style={{ paddingBottom: 24 }}>
                  <p style={{ marginBottom: 12 }}>Shared drawer shell for event details.</p>
                  <p style={{ margin: 0 }}>Business-specific information stays outside the shared layer.</p>
                </div>
              )}
              events={demoEvents}
              renderTimelineContent={(item) => item.content}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader spacing="compact" title="Default header" titleClassName="text-sm font-semibold" />
              <EventDetailHeader
                levelLabel="Critical"
                levelColor="#ff4d4f"
                title="CPU utilization threshold alert"
                activeTab="information"
                tabs={[
                  { key: 'information', label: 'Information' },
                  { key: 'timeline', label: 'Timeline' },
                ]}
                onTabChange={() => undefined}
                metaItems={[
                  { key: 'time', label: 'Time', value: '2026-06-29 10:30:00' },
                  { key: 'state', label: 'State', value: <Tag color="blue">Open</Tag> },
                ]}
              />
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader spacing="compact" title="Monitor-style meta" titleClassName="text-sm font-semibold" />
              <EventDetailHeader
                title="Host memory usage alert"
                levelLabel="Warning"
                levelColor="#faad14"
                activeTab="information"
                tabs={[
                  { key: 'information', label: 'Information' },
                  { key: 'timeline', label: 'Timeline' },
                ]}
                onTabChange={() => undefined}
                metaItems={[
                  { key: 'time', label: 'Time', value: '2026-06-29 10:30:00' },
                  {
                    key: 'alertType',
                    label: 'Alert Type',
                    value: <Tag color="default">Threshold</Tag>,
                  },
                  { key: 'state', label: 'State', value: <Tag color="green">Recovered</Tag> },
                ]}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Timeline detail contract"
          titleClassName="text-sm font-semibold"
          description="Shared event timeline panels keep heatmap navigation and chronological detail playback aligned across monitor and log alert detail flows instead of exposing a separate leaf Storybook page."
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div style={{ height: 420 }}>
              <EventTimelinePanel<DemoEvent>
                events={demoEvents}
                renderTimelineContent={(item) => item.content}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div style={{ height: 420 }}>
              <EventTimelinePanel<DemoEvent>
                events={[
                  ...demoEvents,
                  {
                    id: '3',
                    event_time: '2026-06-24T10:30:00.000Z',
                    content: 'Operator acknowledged and linked the alert to ticket INC-1032',
                  },
                ]}
                renderTimelineContent={(item) => (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-[var(--color-text-1)]">
                      {new Date(item.event_time).toLocaleString()}
                    </span>
                    <span className="text-[var(--color-text-2)]">{item.content}</span>
                    <Button type="link" size="small" className="px-0">
                      Detail
                    </Button>
                  </div>
                )}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Shared alert information summary"
          titleClassName="text-sm font-semibold"
        />
        <div className="space-y-4">
          <div className="max-w-[920px]">
            <EventAlertInformationSummary
              title="Information"
              items={[
                {
                  key: 'time',
                  label: 'Time',
                  value: '2026-06-30 09:45:00',
                },
                {
                  key: 'level',
                  label: 'Level',
                  value: <EventLevelIndicator label="Critical" color="var(--color-error)" />,
                },
                {
                  key: 'firstAlertTime',
                  label: 'First Alert Time',
                  value: '2026-06-30 09:30:00',
                },
                {
                  key: 'information',
                  label: 'Information',
                  value: 'Cross-app shared event summary used by both monitor and log detail flows.',
                  span: 3,
                },
                {
                  key: 'source',
                  label: 'Source',
                  value: 'monitor / log',
                },
                {
                  key: 'strategyName',
                  label: 'Strategy Name',
                  value: 'shared event detail contract',
                },
                {
                  key: 'notify',
                  label: 'Notify',
                  value: 'Notified',
                },
                {
                  key: 'operator',
                  label: 'Operator',
                  value: 'admin',
                },
                {
                  key: 'notifier',
                  label: 'Notifier',
                  value: 'Alice, Bob',
                },
              ]}
              actionsClassName="mt-4 flex justify-between"
              actions={
                <>
                  <EventCloseAction
                    scope="monitor.events"
                    label="Close Alert"
                    disabled={false}
                    loading={false}
                    requiredPermissions={['Operate', 'Detail']}
                    instPermissions={['Operate', 'Detail']}
                    onConfirm={() => undefined}
                  />
                  <Button type="link">See more</Button>
                </>
              }
            />
          </div>

          <div className="max-w-[920px]">
            <EventAlertInformationSummary
              title="Information"
              items={[
                {
                  key: 'time',
                  label: 'Time',
                  value: '2026-06-29 10:30:00',
                },
                {
                  key: 'level',
                  label: 'Level',
                  value: <EventLevelIndicator label="Warning" color="var(--color-warning)" />,
                },
                {
                  key: 'firstAlertTime',
                  label: 'First Alert Time',
                  value: '2026-06-29 10:25:00',
                },
                {
                  key: 'collectType',
                  label: 'Collect Type',
                  value: 'Filebeat',
                  span: 3,
                },
                {
                  key: 'alertType',
                  label: 'Alert Type',
                  value: 'Aggregation Alert',
                },
                {
                  key: 'organizations',
                  label: 'Organizations',
                  value: 'Platform / Observability',
                },
                {
                  key: 'strategyName',
                  label: 'Strategy Name',
                  value: 'nginx error burst',
                },
                {
                  key: 'notify',
                  label: 'Notify',
                  value: 'Notified',
                },
                {
                  key: 'operator',
                  label: 'Operator',
                  value: 'admin',
                },
                {
                  key: 'notifier',
                  label: 'Notifier',
                  value: 'Alice, Bob',
                },
              ]}
              actionsClassName="mt-4 flex justify-between"
              actions={
                <>
                  <EventCloseAction
                    scope="log.event"
                    label="Close Alert"
                    disabled={false}
                    loading={false}
                    requiredPermissions={['Operate', 'Detail']}
                    instPermissions={['Operate', 'Detail']}
                    onConfirm={() => undefined}
                  />
                  <Button type="link">See more</Button>
                </>
              }
            />
          </div>

          <div className="max-w-[920px]">
            <EventAlertInformationSummary
              title="Information"
              items={[
                {
                  key: 'time',
                  label: 'Time',
                  value: '2026-06-29 10:30:00',
                },
                {
                  key: 'level',
                  label: 'Level',
                  value: <EventLevelIndicator label="Warning" color="var(--color-warning)" />,
                },
                {
                  key: 'firstAlertTime',
                  label: 'First Alert Time',
                  value: '2026-06-29 10:25:00',
                },
                {
                  key: 'information',
                  label: 'Information',
                  value: 'CPU usage exceeded 90% for 5 minutes',
                  span: 3,
                },
                {
                  key: 'assetType',
                  label: 'Asset Type',
                  value: 'Host',
                },
                {
                  key: 'asset',
                  label: 'Asset',
                  value: (
                    <div className="flex justify-between items-center">
                      <span className="flex-1">host-01</span>
                      <a href="#" className="text-blue-500 ml-2">
                        More
                      </a>
                    </div>
                  ),
                },
                {
                  key: 'assetGroup',
                  label: 'Asset Group',
                  value: 'Platform / Production',
                },
                {
                  key: 'strategyName',
                  label: 'Strategy Name',
                  value: 'cpu saturation',
                },
                {
                  key: 'notify',
                  label: 'Notify',
                  value: 'Unnotified',
                },
                {
                  key: 'operator',
                  label: 'Operator',
                  value: '--',
                },
                {
                  key: 'notifier',
                  label: 'Notifier',
                  value: 'Carol',
                },
              ]}
              actions={
                <EventCloseAction
                  scope="monitor.events"
                  label="Close Alert"
                  disabled={false}
                  loading={false}
                  requiredPermissions={['Operate', 'Detail']}
                  instPermissions={['Operate', 'Detail']}
                  onConfirm={() => undefined}
                />
              }
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Event alert workspace shell"
          titleClassName="text-sm font-semibold"
          description="Monitor and log alert pages share the same event-alert workspace shell; the stable differences live in filter controls, chart hint copy, and whether state filtering is present."
        />
        <div className="space-y-4">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Log alert workflow" titleClassName="text-sm font-semibold" />
            <EventAlertWorkspaceShell
              activeTab="activeAlarms"
              tabs={eventAlertTabs}
              onTabChange={() => undefined}
              filterPanel={(
                <FilterToolbar spacing="flush" contentClassName="gap-4" align="between">
                  <div className="flex items-center">
                    <span className="mr-[8px] text-[12px] text-[var(--color-text-3)]">Level</span>
                    <Select style={{ width: 200 }} options={[{ value: 'critical', label: 'Critical' }]} />
                  </div>
                  <TimeSelector onlyRefresh onFrequenceChange={() => undefined} onRefresh={() => undefined} />
                </FilterToolbar>
              )}
              chartTitle="Distribution map"
              chartContent={<StackedBarChart data={eventAlertChartData} colors={{ critical: '#f04438', warning: '#f79009', error: '#6172f3' } as any} />}
              searchProps={{
                allowClear: true,
                className: 'w-[240px]',
                placeholder: 'Search alerts',
                enterButton: true,
              }}
              columns={[
                { title: 'Level', dataIndex: 'level', key: 'level' },
                { title: 'Name', dataIndex: 'name', key: 'name' },
                { title: 'State', dataIndex: 'state', key: 'state' },
              ]}
              dataSource={eventAlertTableData}
              rowKey="id"
              pagination={{ current: 1, total: 2, pageSize: 20 }}
              scroll={{ y: 320, x: 'max-content' }}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Monitor alert workflow" titleClassName="text-sm font-semibold" />
            <EventAlertWorkspaceShell
              activeTab="activeAlarms"
              tabs={eventAlertTabs}
              onTabChange={() => undefined}
              filterPanel={(
                <>
                  <div className="mb-[10px]">Search criteria</div>
                  <FilterToolbar spacing="flush" contentClassName="gap-4" align="between">
                    <div className="flex items-center gap-[8px]">
                      <div>
                        <span className="mr-[8px] text-[12px] text-[var(--color-text-3)]">Level</span>
                        <Select
                          style={{ width: 200 }}
                          options={[{ value: 'critical', label: 'Critical' }]}
                        />
                      </div>
                      <div>
                        <span className="mr-[8px] text-[12px] text-[var(--color-text-3)]">State</span>
                        <Select
                          style={{ width: 200 }}
                          options={[{ value: 'new', label: 'Open' }]}
                        />
                      </div>
                    </div>
                    <TimeSelector onlyRefresh onFrequenceChange={() => undefined} onRefresh={() => undefined} />
                  </FilterToolbar>
                </>
              )}
              chartTitle="Distribution map"
              chartHint={(
                <Tooltip placement="top" title="Monitor alert distribution details">
                  <div
                    className="absolute cursor-pointer"
                    style={{ top: '-4px', right: '-14px' }}
                  >
                    <Icon
                      type="a-shuoming2"
                      className="text-[14px] text-[var(--color-text-3)]"
                    />
                  </div>
                </Tooltip>
              )}
              chartContent={<StackedBarChart data={eventAlertChartData} colors={{ critical: '#f04438', warning: '#f79009', error: '#6172f3' } as any} />}
              searchProps={{
                allowClear: true,
                className: 'w-[240px]',
                placeholder: 'Search alerts',
                enterButton: true,
              }}
              columns={[
                { title: 'Level', dataIndex: 'level', key: 'level' },
                { title: 'Name', dataIndex: 'name', key: 'name' },
                { title: 'State', dataIndex: 'state', key: 'state' },
              ]}
              dataSource={eventAlertTableData}
              rowKey="id"
              pagination={{ current: 1, total: 2, pageSize: 20 }}
              scroll={{ y: 320, x: 'max-content' }}
            />
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_420px]">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader
            spacing="flush"
            title="Notification strategy contract"
            titleClassName="text-sm font-semibold"
          />
          <div className="space-y-6">
            <Form
              layout="horizontal"
              initialValues={{
                notice: true,
                notice_type_id: 1,
                notice_type_ids: [1, 2],
                notice_users: [101, 103],
              }}
              labelCol={{ flex: '120px' }}
              wrapperCol={{ flex: 1 }}
            >
              <EventNotificationForm
                channelFieldName="notice_type_ids"
                channelList={[...channels]}
                channelSelectionMode="multiple"
                {...createMonitorEventNotificationPreset(t)}
                userList={users}
                onLinkToSystemManage={() => undefined}
                selectStyle={{ width: '100%' }}
              />
            </Form>

            <Form
              layout="horizontal"
              initialValues={{
                notice: true,
                notice_type_id: 1,
                notice_type_ids: [1, 2],
                notice_users: [101, 103],
              }}
              labelCol={{ flex: '120px' }}
              wrapperCol={{ flex: 1 }}
            >
              <EventNotificationForm
                channelFieldName="notice_type_id"
                channelList={[...channels]}
                channelSelectionMode="single"
                userList={users}
                onLinkToSystemManage={() => undefined}
                resolveNotifierMode={() => 'users'}
                copy={{
                  configDescription: t('event.strategy.notifications.description'),
                  configLabel: t('event.strategy.notifications.title'),
                  channelLabel: t('event.strategy.notifications.channel'),
                  notifierLabel: t('event.strategy.notifications.user'),
                  emptyStatePrefix: '',
                  emptyStateLinkLabel: '',
                  emptyStateSuffix: '',
                  notifierPlaceholder: '',
                  requiredMessage: '',
                }}
                cardGridStyle={{ maxWidth: 800 }}
                selectStyle={{ width: '800px' }}
              />
            </Form>
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Strategy side panels" titleClassName="text-sm font-semibold" />
          <div className="space-y-4">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader spacing="compact" title="Identity fields: log" titleClassName="text-sm font-semibold" />
              <Form layout="vertical">
                <EventStrategyIdentityFields
                  strategyNameLabel={<span className="w-[100px]">Strategy Name</span>}
                  strategyNamePlaceholder="Keyword anomaly strategy"
                  organizationLabel={<span className="w-[100px]">Organizations</span>}
                  organizationPlaceholder="Organizations"
                  requiredMessage="Required"
                  strategyInputClassName="w-[800px]"
                  organizationSelectorStyle={{
                    width: '800px',
                    marginRight: '8px',
                  }}
                />
              </Form>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader spacing="compact" title="Identity fields: monitor" titleClassName="text-sm font-semibold" />
              <Form layout="vertical">
                <EventStrategyIdentityFields
                  strategyNameLabel={<span className="w-[100px]">Strategy Name</span>}
                  strategyNamePlaceholder="CPU saturation strategy"
                  organizationLabel={<span className="w-[100px]">Group</span>}
                  organizationPlaceholder="Select group"
                  requiredMessage="Required"
                  strategyInputClassName="w-full"
                  organizationSelectorStyle={{
                    width: '100%',
                    marginRight: '8px',
                  }}
                  organizationDescription="Associate the policy with the owning monitor group."
                />
              </Form>
            </div>

            <EventStrategyPanel
              title="Available Variables"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[var(--color-text-2)]">${'{resource_name}'}</span>
                  <Button size="small">Use</Button>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[var(--color-text-2)]">${'{level}'}</span>
                  <Button size="small">Use</Button>
                </div>
              </div>
            </EventStrategyPanel>

            <EventStrategyPanel
              title="Metric Preview"
              extra={(
                <Select
                  value="node-1"
                  style={{ width: 180 }}
                  options={[
                    { label: 'Node 1', value: 'node-1' },
                    { label: 'Node 2', value: 'node-2' },
                  ]}
                />
              )}
            >
              <div className="h-[180px] rounded border border-dashed border-[var(--color-border)] bg-[var(--color-bg-2)]" />
            </EventStrategyPanel>

            <EventStrategyPanel
              title="Threshold Rules"
              stickyTop={24}
            >
              <div className="space-y-3">
                <div className="rounded-md border border-[var(--color-border-2)] p-3">Critical greater than 90</div>
                <div className="rounded-md border border-[var(--color-border-2)] p-3">Warning greater than 70</div>
              </div>
            </EventStrategyPanel>

            <EventStrategyPanel
              extra={(
                <div className="flex items-center gap-2">
                  <span className="text-[12px] text-[var(--color-text-3)]">Unit:</span>
                  <Select
                    value="cpu"
                    style={{ width: 160 }}
                    options={[
                      { label: 'CPU %', value: 'cpu' },
                      { label: 'Memory MiB', value: 'memory' },
                    ]}
                  />
                </div>
              )}
            >
              <div className="space-y-3">
                <div className="rounded-md border border-[var(--color-border-2)] p-3">Critical greater than 90</div>
                <div className="rounded-md border border-[var(--color-border-2)] p-3">Warning greater than 70</div>
              </div>
            </EventStrategyPanel>
          </div>
        </section>
      </div>
    </div>
  );
};

const meta = {
  title: 'Business/Events/FamilyOverview',
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
