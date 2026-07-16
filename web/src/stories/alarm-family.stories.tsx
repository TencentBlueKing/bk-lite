import React, { useEffect, useRef, useState } from 'react';
import type { Meta, StoryObj } from '@storybook/react';
import { Breadcrumb, Button, Form, message } from 'antd';
import AlarmEffectiveTime from '@/app/alarm/components/alarm-effective-time';
import AlarmAction from '@/app/alarm/components/alarm-action';
import AlarmAssignModal from '@/app/alarm/components/alarm-action/assign-modal';
import AlarmBaseInfo from '@/app/alarm/components/alarm-base-info';
import AlarmDetailDrawer from '@/app/alarm/components/alarm-detail-drawer';
import AlarmEventTable from '@/app/alarm/components/alarm-event-table';
import AlarmFilters, { type AlarmFiltersValue } from '@/app/alarm/components/alarm-filters';
import AlarmLevelIcon from '@/app/alarm/components/alarm-level-icon';
import AlarmMatchRule from '@/app/alarm/components/alarm-match-rule';
import AlarmPageBreadcrumb from '@/app/alarm/components/alarm-page-breadcrumb';
import { defaultAlarmBreadcrumbMenus } from '@/app/alarm/components/alarm-page-breadcrumb/menu';
import AlarmRuleScopeField from '@/app/alarm/components/alarm-rule-scope-field';
import AlarmSearchFilter from '@/app/alarm/components/alarm-search-filter';
import AlarmTable from '@/app/alarm/components/alarm-table';
import DeclareIncident from '@/components/declare-incident';
import RelatedAlertsPanel from '@/app/alarm/components/related-alerts-panel';
import SectionHeader from '@/components/section-header';

interface AlarmDetailDrawerStoryRef {
  showModal: (config: {
    title: string;
    form: Record<string, unknown>;
    defaultTab?: string;
  }) => void;
}

const levelOptions = [
  { value: '2', label: 'High', color: '#f97316', icon: 'warning-solid' },
  { value: '3', label: 'Medium', color: '#facc15', icon: 'warning-solid' },
];

const assigneeOptions = [
  { label: 'Alice (alice)', value: 'alice' },
  { label: 'Bob (bob)', value: 'bob' },
];

const sampleAlert = {
  id: 1,
  alert_id: 'alert-1001',
  incident_id: 'incident-1',
  level: '2',
  status: 'processing',
  title: 'CPU threshold reached',
  content: 'CPU usage stayed above 90% for 10 minutes.',
  duration: '10m',
  first_event_time: '2026-06-25T10:00:00Z',
  last_event_time: '2026-06-25T10:10:00Z',
  operator_user: 'alice',
  operator: ['alice'],
  source_names: 'host-monitor',
  notification_status: 'success',
  resource_type: 'host',
  resource_name: 'vm-01',
  incident_name: 'Host performance incident',
  event_count: 4,
  created_at: '2026-06-25T10:00:00Z',
  enrichment: {
    labels: {
      cluster: 'prod-a',
      region: 'cn-east',
    },
  },
};

const StorySearchFilter = () => {
  const [lastSearch, setLastSearch] = useState<string>('No search yet');

  return (
    <div className="space-y-3">
      <AlarmSearchFilter
        attrList={[
          { attr_id: 'title', attr_name: 'Title', attr_type: 'string' },
          {
            attr_id: 'status',
            attr_name: 'Status',
            attr_type: 'enum',
            option: [
              { id: 'processing', name: 'Processing' },
              { id: 'closed', name: 'Closed' },
            ],
          },
        ]}
        onSearch={(condition) => {
          setLastSearch(JSON.stringify(condition));
        }}
      />
      <div className="text-sm text-[var(--color-text-3)]">{lastSearch}</div>
    </div>
  );
};

const AutoOpenDeclareIncidentDemo = () => {
  const containerRef = React.useRef<HTMLDivElement>(null);

  useEffect(() => {
    const button = containerRef.current?.querySelector('button');
    if (button instanceof HTMLButtonElement) {
      button.click();
    }
  }, []);

  return (
    <div ref={containerRef}>
      <DeclareIncident
        rowData={[
          {
            id: 1,
            title: 'CPU threshold reached',
            has_incident: false,
          },
        ]}
        onSuccess={() => undefined}
        currentUsername="admin"
        initialTeamIds={[1]}
        assigneeOptions={[
          { label: 'Admin (admin)', value: 'admin' },
          { label: 'Alice (alice)', value: 'alice' },
        ]}
        levelOptions={[
          { label: 'P1', value: '1' },
          { label: 'P2', value: '2' },
        ]}
        fetchIncidentList={async () => [
          { id: 1, title: 'Database incident', alert: [9] } as any,
          { id: 2, title: 'Network incident', alert: [] } as any,
        ]}
        createIncident={async () => ({})}
        updateIncident={async () => ({})}
      />
    </div>
  );
};

const AlarmRuleScopeDemo: React.FC<{
  initialValues?: Record<string, unknown>;
  label: string;
  allLabel: string;
  filterLabel: string;
  placeholder: string;
}> = ({ initialValues, label, allLabel, filterLabel, placeholder }) => {
  const [form] = Form.useForm();
  const [scopeValue, setScopeValue] = React.useState<'all' | 'filter' | undefined>(
    initialValues?.match_type as 'all' | 'filter' | undefined
  );

  return (
    <Form
      form={form}
      layout="horizontal"
      labelCol={{ span: 4 }}
      initialValues={initialValues}
    >
      <AlarmRuleScopeField
        form={form}
        label={label}
        allLabel={allLabel}
        filterLabel={filterLabel}
        requiredMessage="Required"
        scopeValue={scopeValue}
        onScopeChange={setScopeValue}
        radioVariant={
          (initialValues?.radioVariant as 'default' | 'button' | undefined) ||
          'default'
        }
        validateMatchRules={
          (initialValues?.validateMatchRules as boolean | undefined) ?? true
        }
        matchRulesClassName="mb-0"
        levelOffsetStyle={{ marginTop: 0, marginBottom: 0, marginLeft: '110px' }}
        matchRuleNode={(
          <div className="rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-bg-2)] p-4 text-sm text-[var(--color-text-2)]">
            {placeholder}
          </div>
        )}
      />
    </Form>
  );
};

const AlarmBreadcrumbDemo = () => (
  <div className="space-y-4">
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
      <SectionHeader
        spacing="compact"
        title="Incident detail breadcrumb"
        titleClassName="text-sm font-medium"
      />
      <div className="mt-3">
        <AlarmPageBreadcrumb
          pathnameOverride="/alarm/incidents/detail"
          localeOverride="en"
          menus={defaultAlarmBreadcrumbMenus}
          onNavigate={(path) => {
            void message.info(`Navigate to ${path}`);
          }}
        >
          <Breadcrumb.Item>Demo incident</Breadcrumb.Item>
        </AlarmPageBreadcrumb>
      </div>
    </div>

    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
      <SectionHeader
        spacing="compact"
        title="Integration detail breadcrumb"
        titleClassName="text-sm font-medium"
      />
      <div className="mt-3">
        <AlarmPageBreadcrumb
          pathnameOverride="/alarm/integration/detail"
          localeOverride="en"
          menus={defaultAlarmBreadcrumbMenus}
          onNavigate={() => undefined}
        />
      </div>
    </div>
  </div>
);

const AlarmAssignModalDemo = () => {
  const [visibleAction, setVisibleAction] = React.useState<'assign' | 'reassign' | null>(
    null
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3">
        <Button type="primary" onClick={() => setVisibleAction('assign')}>
          Open assign modal
        </Button>
        <Button onClick={() => setVisibleAction('reassign')}>Open reassign modal</Button>
      </div>
      <div className="text-sm text-[var(--color-text-3)]">
        The assign modal is governed as an internal state of the alarm action workflow.
      </div>
      <AlarmAssignModal
        visible={visibleAction !== null}
        actionType={visibleAction || 'assign'}
        alertIds={[101, 102]}
        assigneeOptions={[
          { label: 'Alice (alice)', value: 'alice' },
          { label: 'Bob (bob)', value: 'bob' },
          { label: 'Charlie (charlie)', value: 'charlie' },
        ]}
        operateAction={async () => ({ mock: { result: true } })}
        onCancel={() => setVisibleAction(null)}
        onSuccess={() => setVisibleAction(null)}
      />
    </div>
  );
};

const AlarmFamilyOverview = () => {
  const [filters, setFilters] = useState<AlarmFiltersValue>({
    level: ['2'],
    state: ['processing'],
    alarm_source: ['Prometheus'],
  });
  const detailRef = useRef<AlarmDetailDrawerStoryRef>(null);

  useEffect(() => {
    detailRef.current?.showModal({
      title: sampleAlert.title,
      form: sampleAlert,
      defaultTab: 'baseInfo',
    });
  }, []);

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Alarm list workspace"
          titleClassName="text-sm font-semibold"
          description="Shared filters, search, table, and row actions used across alarm and incident list flows."
        />

        <div className="space-y-4">
          <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader
              spacing="flush"
              title="Alarm navigation and display primitives"
              titleClassName="text-sm font-medium"
              description="Breadcrumb and severity icon treatments are small alarm-domain building blocks, so their variants stay governed inside the family instead of becoming standalone Storybook roots."
            />

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
              <AlarmBreadcrumbDemo />

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
                <SectionHeader
                  spacing="compact"
                  title="Alarm level icon variants"
                  titleClassName="text-sm font-medium"
                />
                <div className="mt-3 space-y-3">
                  <div className="flex items-center gap-3 text-sm text-[var(--color-text-2)]">
                    <span className="w-28 shrink-0">Icon font</span>
                    <AlarmLevelIcon icon="warning" className="h-4 w-4 text-red-500" />
                  </div>
                  <div className="flex items-center gap-3 text-sm text-[var(--color-text-2)]">
                    <span className="w-28 shrink-0">Inline image</span>
                    <AlarmLevelIcon
                      icon={'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="%23faad14"/></svg>'}
                      className="h-4 w-4"
                    />
                  </div>
                  <div className="flex items-center gap-3 text-sm text-[var(--color-text-2)]">
                    <span className="w-28 shrink-0">Empty fallback</span>
                    <AlarmLevelIcon />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader
              className="mb-3"
              title="Source-aware filtering"
              titleClassName="text-sm font-medium"
              description="The main alarm list branch includes source selection alongside severity and state filters."
            />
            <AlarmFilters
              filters={filters}
              levelOptions={[
                { value: '1', label: 'Critical', color: '#ef4444' },
                { value: '2', label: 'High', color: '#f97316' },
                { value: '3', label: 'Medium', color: '#facc15' },
              ]}
              stateOptions={[
                { value: 'pending', label: 'Pending' },
                { value: 'processing', label: 'Processing' },
                { value: 'closed', label: 'Closed' },
              ]}
              sourceOptions={[
                { value: 'Prometheus', label: 'Prometheus' },
                { value: 'CloudWatch', label: 'CloudWatch' },
              ]}
              onFilterChange={(vals, field) =>
                setFilters((prev) => ({ ...prev, [field]: vals }))
              }
              clearFilters={(field) =>
                setFilters((prev) => ({ ...prev, [field]: [] }))
              }
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
            <SectionHeader
              className="mb-3"
              title="Compact filtering without source"
              titleClassName="text-sm font-medium"
              description="The same alarm filter contract also supports compact list surfaces that only expose level and state filters."
            />
            <AlarmFilters
              filters={{
                level: ['2'],
                state: ['pending'],
                alarm_source: [],
              }}
              filterSource={false}
              levelOptions={[
                { value: '1', label: 'Critical', color: '#ef4444' },
                { value: '2', label: 'High', color: '#f97316' },
                { value: '3', label: 'Medium', color: '#facc15' },
              ]}
              stateOptions={[
                { value: 'pending', label: 'Pending' },
                { value: 'processing', label: 'Processing' },
                { value: 'closed', label: 'Closed' },
              ]}
              onFilterChange={() => undefined}
              clearFilters={() => undefined}
            />
          </div>
        </div>

        <StorySearchFilter />

        <div className="flex flex-wrap gap-3">
          <AlarmAction
            rowData={[sampleAlert]}
            currentUsername="alice"
            assigneeOptions={assigneeOptions}
            operateAction={async () => ({ mock: { result: true } })}
            onAction={() => undefined}
          />
          <DeclareIncident
            rowData={[sampleAlert]}
            onSuccess={() => undefined}
            currentUsername="alice"
            initialTeamIds={[1]}
            assigneeOptions={assigneeOptions}
            levelOptions={[
              { label: 'P1', value: '1' },
              { label: 'P2', value: '2' },
            ]}
            fetchIncidentList={async () => [
              { id: 1, title: 'Database incident', alert: [9] } as any,
              { id: 2, title: 'Network incident', alert: [] } as any,
            ]}
            createIncident={async () => ({})}
            updateIncident={async () => ({})}
          />
        </div>

        <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
          <SectionHeader
            spacing="flush"
            title="Incident declaration variants"
            titleClassName="text-sm font-medium"
            description="The alarm workspace family also keeps the closed button state and the opened declare-incident modal state inside the same workflow contract."
          />
          <div className="grid gap-4 xl:grid-cols-2">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
              <SectionHeader spacing="compact" title="Closed state" titleClassName="text-sm font-medium" />
              <div className="mt-3">
                <DeclareIncident
                  rowData={[
                    {
                      id: 1,
                      title: 'CPU threshold reached',
                      has_incident: false,
                    },
                  ]}
                  onSuccess={() => undefined}
                  currentUsername="admin"
                  initialTeamIds={[1]}
                  assigneeOptions={[
                    { label: 'Admin (admin)', value: 'admin' },
                    { label: 'Alice (alice)', value: 'alice' },
                  ]}
                  levelOptions={[
                    { label: 'P1', value: '1' },
                    { label: 'P2', value: '2' },
                  ]}
                  fetchIncidentList={async () => [
                    { id: 1, title: 'Database incident', alert: [9] } as any,
                    { id: 2, title: 'Network incident', alert: [] } as any,
                  ]}
                  createIncident={async () => ({})}
                  updateIncident={async () => ({})}
                />
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
              <SectionHeader spacing="compact" title="Opened modal" titleClassName="text-sm font-medium" />
              <div className="mt-3 min-h-[280px]">
                <AutoOpenDeclareIncidentDemo />
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
          <SectionHeader
            spacing="flush"
            title="Alarm action variants"
            titleClassName="text-sm font-medium"
            description="The alarm workspace contract also governs dropdown and incident-context action branches without needing separate Storybook roots."
          />

          <div className="flex flex-wrap gap-3">
            <AlarmAction
              rowData={[sampleAlert]}
              displayMode="dropdown"
              currentUsername="alice"
              assigneeOptions={assigneeOptions}
              operateAction={async () => ({ mock: { result: true } })}
              onAction={() => undefined}
            />
            <AlarmAction
              rowData={[{ ...sampleAlert, status: 'closed' }]}
              from="incident"
              showAll={true}
              currentUsername="alice"
              assigneeOptions={assigneeOptions}
              operateAction={async () => ({ mock: { result: true } })}
              onAction={() => undefined}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
            <SectionHeader
              spacing="compact"
              title="Assign modal states"
              titleClassName="text-sm font-medium"
              description="Assign and reassign modal branches stay inside the same alarm action workflow contract instead of splitting into a standalone Storybook root."
            />
            <div className="mt-3">
              <AlarmAssignModalDemo />
            </div>
          </div>
        </div>

        <AlarmTable
          readonly={true}
          loading={false}
          tableScrollY="320px"
          selectedRowKeys={[]}
          levelOptions={levelOptions}
          detailFetchEventList={async () => ({
            items: [],
            count: 0,
          })}
          detailFetchLogList={async () => ({
            items: [],
          })}
          fetchRelatedAlerts={async () => ({
            related_count: 0,
            maybe_related_count: 0,
            current_incidents: [],
            items: [],
          })}
          addAlertsToIncidentAction={async () => ({})}
          onSelectionChange={() => undefined}
          onChange={() => undefined}
          onRefresh={() => undefined}
          pagination={{
            current: 1,
            pageSize: 10,
            total: 2,
          }}
          dataSource={[
            sampleAlert,
            {
              ...sampleAlert,
              id: 2,
              alert_id: 'alert-1002',
              level: '3',
              status: 'closed',
              title: 'Disk warning',
              incident_name: '',
              event_count: 2,
              duration: '15m',
              operator_user: 'bob',
              notify_status: 'failed',
              content: 'Disk usage above 80%',
              created_at: '2026-06-25T11:00:00Z',
              first_event_time: '2026-06-25T11:00:00Z',
              last_event_time: '2026-06-25T11:15:00Z',
            },
          ]}
        />

        <AlarmEventTable
          dataSource={[
            {
              id: 'evt-1',
              start_time: '2026-07-13T10:00:00Z',
              source_name: 'prometheus-cluster',
              title: 'CPU spike on node-1',
              resource_type: 'host',
              status: 'firing',
              item: 'cpu_usage',
              value: 92,
              level: '2',
              raw_data: {
                labels: { instance: 'node-1', job: 'node-exporter' },
                annotations: { summary: 'CPU above 90% for 5m' },
              },
            },
            {
              id: 'evt-2',
              start_time: '2026-07-13T10:15:00Z',
              source_name: 'cloudwatch-rds',
              title: 'DB connections high',
              resource_type: 'rds',
              status: 'received',
              item: 'db_connections',
              value: 480,
              level: '3',
              raw_data: { engine: 'postgres', region: 'us-east-1' },
            },
          ]}
          levelOptions={levelOptions}
          pagination={{ current: 1, pageSize: 10, total: 2 }}
          onChange={() => undefined}
          tableScrollY="240px"
        />
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Rule configuration primitives"
          titleClassName="text-sm font-semibold"
          description="Alert assignment, shield strategy, enrichment, and correlation settings now share governed rule-matching and effective-time components instead of burying those contracts inside page-local settings helpers."
        />

        <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <AlarmMatchRule
            value={[[{ key: 'resource_type', operator: 'eq', value: 'host' }]]}
            onChange={() => undefined}
            levelType="event"
            sourceOptions={[
              { id: '1', name: 'Prometheus' } as any,
              { id: '2', name: 'CloudWatch' } as any,
            ]}
            levelOptionsOverride={[
              { level_id: '1', level_display_name: 'Critical' },
              { level_id: '2', level_display_name: 'Warning' },
            ]}
          />
          <AlarmEffectiveTime
            open
            value={{
              type: 'week',
              week_month: [1, 3, 5],
              start_time: '09:00:00',
              end_time: '18:00:00',
            }}
            onChange={() => undefined}
          />
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader
              spacing="compact"
              title="Multi-group match rule"
              titleClassName="text-sm font-medium"
              description="The same governed matching contract also supports multiple condition groups without needing a separate Storybook page."
            />
            <AlarmMatchRule
              value={[
                [{ key: 'resource_type', operator: 'eq', value: 'host' }],
                [
                  { key: 'level', operator: 'eq', value: '1' },
                  { key: 'source_id', operator: 'eq', value: '2' },
                ],
              ]}
              onChange={() => undefined}
              levelType="event"
              sourceOptions={[
                { id: '1', name: 'Prometheus' } as any,
                { id: '2', name: 'CloudWatch' } as any,
              ]}
              levelOptionsOverride={[
                { level_id: '1', level_display_name: 'Critical' },
                { level_id: '2', level_display_name: 'Warning' },
              ]}
            />
          </div>

          <div className="space-y-4">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader
                spacing="compact"
                title="One-time effective window"
                titleClassName="text-sm font-medium"
              />
              <AlarmEffectiveTime
                open
                value={{
                  type: 'one',
                  week_month: [],
                  start_time: '2026-07-01 09:00:00',
                  end_time: '2026-07-03 18:00:00',
                }}
                onChange={() => undefined}
              />
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <SectionHeader
                spacing="compact"
                title="Daily effective window"
                titleClassName="text-sm font-medium"
              />
              <AlarmEffectiveTime
                open
                value={{
                  type: 'day',
                  week_month: [],
                  start_time: '09:00:00',
                  end_time: '18:00:00',
                }}
                onChange={() => undefined}
              />
            </div>
          </div>
        </div>

        <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SectionHeader
            spacing="flush"
            title="Rule scope field variants"
            titleClassName="text-sm font-medium"
            description="The shared scope toggle for alert assign, shield strategy, and enrichment settings stays governed inside the same rule-configuration family instead of splitting into a separate settings leaf."
          />
          <div className="grid gap-4 xl:grid-cols-2">
            <div className="space-y-4">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
                <SectionHeader spacing="compact" title="All scope" titleClassName="text-sm font-medium" />
                <div className="mt-3">
                  <AlarmRuleScopeDemo
                    initialValues={{ match_type: 'all' }}
                    label="Matching rules"
                    allLabel="All"
                    filterLabel="Filter"
                    placeholder="Match rule editor appears when filter mode is enabled."
                  />
                </div>
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
                <SectionHeader spacing="compact" title="Filter scope" titleClassName="text-sm font-medium" />
                <div className="mt-3">
                  <AlarmRuleScopeDemo
                    initialValues={{
                      match_type: 'filter',
                      match_rules: [[{ key: 'title', operator: 'contains', value: 'cpu' }]],
                    }}
                    label="Matching rules"
                    allLabel="All"
                    filterLabel="Filter"
                    placeholder="Configured alert/event match rules render inside this slot."
                  />
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
              <SectionHeader spacing="compact" title="Button-style scope" titleClassName="text-sm font-medium" />
              <div className="mt-3">
                <AlarmRuleScopeDemo
                  initialValues={{
                    match_type: 'filter',
                    radioVariant: 'button',
                    validateMatchRules: false,
                    match_rules: [[{ key: 'resource_type', operator: 'eq', value: '' }]],
                  }}
                  label="Enrichment scope"
                  allLabel="All events"
                  filterLabel="Filter events"
                  placeholder="Button-style scope switch with relaxed validation for partially authored enrichment rules."
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_420px]">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Alarm detail workflow shell" titleClassName="text-sm font-semibold" />
          <AlarmDetailDrawer
            ref={detailRef}
            levelOptions={levelOptions}
            readonly={false}
            fetchEventList={async () => ({
              items: [
                {
                  id: 11,
                  title: 'CPU overloaded',
                  level: '2',
                  source_name: 'prometheus',
                  received_at: '2026-06-25T10:01:00Z',
                  start_time: '2026-06-25T10:00:00Z',
                  end_time: '2026-06-25T10:10:00Z',
                  description: 'cpu > 90%',
                  status: 'firing',
                  action: '',
                  rule_id: 1,
                  event_id: 'evt-1',
                  external_id: 'ext-1',
                  item: 'cpu_usage',
                  resource_id: 'host-1',
                  resource_type: 'host',
                  resource_name: 'vm-01',
                  assignee: [],
                  note: null,
                  raw_data: {
                    item: 'cpu_usage',
                    level: '2',
                    title: 'CPU overloaded',
                    value: 95,
                    labels: {},
                    status: 'firing',
                    start_time: '2026-06-25T10:00:00Z',
                    end_time: '2026-06-25T10:10:00Z',
                    annotations: {
                      summary: 'cpu > 90%',
                      severity: 'critical',
                      alertname: 'CPU overloaded',
                    },
                    description: 'cpu > 90%',
                    external_id: 'ext-1',
                    resource_id: 1,
                    resource_name: 'vm-01',
                    resource_type: 'host',
                  },
                } as any,
              ],
              count: 1,
            })}
            fetchLogList={async () => ({
              items: [
                {
                  created_at: '2026-06-25T10:02:00Z',
                  operator_object: 'Alert acknowledged',
                  operator: 'alice',
                  overview: 'Operator acknowledged the alert.',
                },
              ],
            })}
            renderRelatedAlerts={() => (
              <div className="rounded-md border border-[var(--color-border)] p-4 text-sm text-[var(--color-text-2)]">
                Related alerts content slot
              </div>
            )}
            renderDeclareIncident={() => (
              <DeclareIncident
                rowData={[sampleAlert]}
                onSuccess={() => undefined}
                currentUsername="alice"
                initialTeamIds={[1]}
                assigneeOptions={assigneeOptions}
                levelOptions={[
                  { label: 'P1', value: '1' },
                  { label: 'P2', value: '2' },
                ]}
                fetchIncidentList={async () => [
                  { id: 1, title: 'Database incident', alert: [9] } as any,
                ]}
                createIncident={async () => ({})}
                updateIncident={async () => ({})}
              />
            )}
            alarmActionProps={{
              currentUsername: 'alice',
              assigneeOptions,
              operateAction: async () => ({ mock: { result: true } }),
            }}
            handleAction={() => undefined}
          />
        </section>

        <div className="space-y-6">
          <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
            <SectionHeader
              spacing="flush"
              title="Readonly alarm detail branch"
              titleClassName="text-sm font-semibold"
              description="Readonly detail review still belongs to the same alarm detail workflow contract and stays governed inside the family story."
            />
            <AlarmDetailDrawer
              levelOptions={levelOptions}
              readonly={true}
              fetchEventList={async () => ({
                items: [
                  {
                    id: 11,
                    title: 'CPU overloaded',
                    level: '2',
                    source_name: 'prometheus',
                    received_at: '2026-06-25T10:01:00Z',
                    start_time: '2026-06-25T10:00:00Z',
                    end_time: '2026-06-25T10:10:00Z',
                    description: 'cpu > 90%',
                    status: 'firing',
                    action: '',
                    rule_id: 1,
                    event_id: 'evt-1',
                    external_id: 'ext-1',
                    item: 'cpu_usage',
                    resource_id: 'host-1',
                    resource_type: 'host',
                    resource_name: 'vm-01',
                    assignee: [],
                    note: null,
                    raw_data: {
                      item: 'cpu_usage',
                      level: '2',
                      title: 'CPU overloaded',
                      value: 95,
                      labels: {},
                      status: 'firing',
                      start_time: '2026-06-25T10:00:00Z',
                      end_time: '2026-06-25T10:10:00Z',
                      annotations: {
                        summary: 'cpu > 90%',
                        severity: 'critical',
                        alertname: 'CPU overloaded',
                      },
                      description: 'cpu > 90%',
                      external_id: 'ext-1',
                      resource_id: 1,
                      resource_name: 'vm-01',
                      resource_type: 'host',
                    },
                  } as any,
                ],
                count: 1,
              })}
              fetchLogList={async () => ({
                items: [
                  {
                    created_at: '2026-06-25T10:02:00Z',
                    operator_object: 'Alert acknowledged',
                    operator: 'alice',
                    overview: 'Operator acknowledged the alert.',
                  },
                ],
              })}
            />
          </section>

          <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
            <SectionHeader
              spacing="flush"
              title="Detail base-info panel states"
              titleClassName="text-sm font-semibold"
              description="AlarmBaseInfo remains a business detail component, but its normal and fallback branches travel inside the same detail workflow contract."
            />
            <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <AlarmBaseInfo
                detail={{
                  content: 'CPU usage stayed above 90% for 10 minutes.',
                  operator_user: 'alice',
                  source_names: 'host-monitor',
                  notification_status: 'success',
                  resource_type: 'host',
                  resource_name: 'vm-01',
                }}
              />
              <AlarmBaseInfo
                detail={{
                  content: '',
                  operator_user: '',
                  source_names: null,
                  notification_status: 'unknown',
                  resource_type: '',
                  resource_name: '',
                }}
              />
            </div>
          </section>
        </div>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="Related alerts coordination" titleClassName="text-sm font-semibold" />
          <div className="space-y-4">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
              <SectionHeader
                className="mb-3"
                title="With related matches"
                titleClassName="text-sm font-medium"
                description="The primary coordination branch shows ranked matches, linked incidents, and merge actions."
              />
              <RelatedAlertsPanel
                alert={sampleAlert as any}
                levelOptions={levelOptions}
                alarmActionProps={{
                  currentUsername: 'alice',
                  assigneeOptions,
                  operateAction: async () => ({ mock: { result: true } }),
                }}
                onRefresh={() => undefined}
                fetchRelatedAlerts={async () => ({
                  related_count: 2,
                  maybe_related_count: 1,
                  current_incidents: [
                    {
                      id: 101,
                      incident_id: 'incident-101',
                      title: 'Host performance incident',
                    },
                  ],
                  items: [
                    {
                      id: 11,
                      alert_id: 'alert-11',
                      title: 'CPU spike on node-1',
                      content: 'CPU > 95%',
                      level: '2',
                      status: 'processing',
                      first_event_time: '2026-06-25T10:00:00Z',
                      last_event_time: '2026-06-25T10:10:00Z',
                      incidents: [],
                      similarity_score: 92,
                      match_reason: '相同服务',
                      matched_dimensions: { service: 'compute' },
                      time_proximity: '5m',
                    },
                    {
                      id: 12,
                      alert_id: 'alert-12',
                      title: 'Memory warning on node-1',
                      content: 'memory > 80%',
                      level: '3',
                      status: 'pending',
                      first_event_time: '2026-06-25T10:04:00Z',
                      last_event_time: '2026-06-25T10:14:00Z',
                      incidents: [
                        {
                          id: 101,
                          incident_id: 'incident-101',
                          title: 'Host performance incident',
                        },
                      ],
                      similarity_score: 78,
                      match_reason: '相同位置',
                      matched_dimensions: { host: 'node-1' },
                      time_proximity: '1m',
                    },
                  ],
                })}
                addAlertsToIncidentAction={async () => ({})}
                detailFetchEventList={async () => ({
                  items: [],
                  count: 0,
                })}
                detailFetchLogList={async () => ({
                  items: [],
                })}
              />
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
              <SectionHeader
                className="mb-3"
                title="Empty related set"
                titleClassName="text-sm font-medium"
                description="The same coordination panel also owns the empty-state branch when no related or maybe-related alerts are returned."
              />
              <RelatedAlertsPanel
                alert={sampleAlert as any}
                levelOptions={levelOptions}
                alarmActionProps={{
                  currentUsername: 'alice',
                  assigneeOptions,
                  operateAction: async () => ({ mock: { result: true } }),
                }}
                onRefresh={() => undefined}
                fetchRelatedAlerts={async () => ({
                  related_count: 0,
                  maybe_related_count: 0,
                  current_incidents: [],
                  items: [],
                })}
                addAlertsToIncidentAction={async () => ({})}
                detailFetchEventList={async () => ({
                  items: [],
                  count: 0,
                })}
                detailFetchLogList={async () => ({
                  items: [],
                })}
              />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

const meta = {
  title: 'Business/Alarm/FamilyOverview',
  component: AlarmFamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1180, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof AlarmFamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
