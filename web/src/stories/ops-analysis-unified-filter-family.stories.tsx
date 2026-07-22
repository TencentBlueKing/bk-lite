import type { Meta, StoryObj } from '@storybook/nextjs';
import React, { useState } from 'react';
import { Button } from 'antd';
import {
  FilterBindingPanel,
  UnifiedFilterBar,
  UnifiedFilterConfigModal,
  type UnifiedFilterLayoutItemLike,
} from '@/app/ops-analysis/components/ops-analysis-unified-filter';
import SectionHeader from '@/components/section-header';
import type {
  DatasourceItem,
  FilterValue,
  ParamItem,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/components/ops-analysis-widgets';

const definitions: UnifiedFilterDefinition[] = [
  {
    id: 'namespace__string',
    key: 'namespace',
    name: 'Namespace',
    type: 'string',
    order: 0,
    enabled: true,
    inputMode: 'organization',
    defaultValue: null,
  },
  {
    id: 'status__string',
    key: 'status',
    name: 'Status',
    type: 'string',
    order: 1,
    enabled: true,
    inputMode: 'radio',
    defaultValue: 'running',
    options: [
      { label: 'Running', value: 'running' },
      { label: 'Stopped', value: 'stopped' },
    ],
  },
  {
    id: 'keyword__string',
    key: 'keyword',
    name: 'Keyword',
    type: 'string',
    order: 2,
    enabled: true,
    inputMode: 'input',
    defaultValue: '',
  },
] as UnifiedFilterDefinition[];

const bindingDefinitions: UnifiedFilterDefinition[] = [
  {
    id: 'namespace__string',
    key: 'namespace',
    name: 'Namespace',
    type: 'string',
    order: 0,
    enabled: true,
    defaultValue: null,
  },
  {
    id: 'time_range__timeRange',
    key: 'time_range',
    name: 'Time Range',
    type: 'timeRange',
    order: 1,
    enabled: false,
    defaultValue: null,
  },
] as UnifiedFilterDefinition[];

const dataSourceParams: ParamItem[] = [
  {
    name: 'namespace',
    alias_name: 'Namespace',
    type: 'string',
    filterType: 'filter',
  } as ParamItem,
  {
    name: 'time_range',
    alias_name: 'Time Range',
    type: 'timeRange',
    filterType: 'filter',
  } as ParamItem,
] as ParamItem[];

const layoutItems: UnifiedFilterLayoutItemLike[] = [
  {
    valueConfig: {
      dataSource: 1,
    },
  } as UnifiedFilterLayoutItemLike,
] as UnifiedFilterLayoutItemLike[];

const dataSources: DatasourceItem[] = [
  {
    id: 1,
    name: 'Prometheus',
    rest_api: '/api/prom/query',
    desc: 'Cluster metric source',
    hasAuth: true,
    params: [
      {
        name: 'namespace',
        alias_name: 'Namespace',
        type: 'string',
        filterType: 'filter',
        value: '',
      },
    ],
  } as DatasourceItem,
  {
    id: 2,
    name: 'MySQL',
    rest_api: '/api/mysql/query',
    desc: 'Restricted source without permission',
    hasAuth: false,
    params: [],
  } as DatasourceItem,
] as DatasourceItem[];

const FamilyOverview = () => {
  const [values, setValues] = useState<Record<string, FilterValue>>({
    status__string: 'running',
    keyword__string: 'error',
  });
  const [filterBindings, setFilterBindings] = useState({
    namespace__string: true,
  });

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Unified filter bar contract"
          titleClassName="text-sm font-semibold"
          description="The query bar keeps default and embedded appearances inside one governed business contract instead of splitting layout variants into separate pages."
        />
        <div className="space-y-4">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <UnifiedFilterBar
              definitions={definitions}
              values={values}
              onChange={setValues}
              onSearch={setValues}
              onReset={setValues}
              prefixContent={<Button size="small">Config</Button>}
            />
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <UnifiedFilterBar
              definitions={definitions}
              values={values}
              onChange={setValues}
              onSearch={setValues}
              onReset={setValues}
              appearance="embedded"
              prefixContent={<Button size="small">Config</Button>}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Binding panel contract"
          titleClassName="text-sm font-semibold"
          description="Binding toggles, disabled filter states, and data-source parameter mapping belong to the same unified filter workflow and stay reviewed together."
        />
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <FilterBindingPanel
              definitions={bindingDefinitions}
              dataSourceParams={dataSourceParams}
              filterBindings={filterBindings}
              onChange={(next) => setFilterBindings(next as { namespace__string: boolean })}
            />
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <FilterBindingPanel
              definitions={bindingDefinitions}
              dataSourceParams={[]}
              filterBindings={{}}
              onChange={() => undefined}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Configuration modal contract"
          titleClassName="text-sm font-semibold"
          description="Definition ordering, default values, and data-source scanning are reviewed as one modal workflow, not as an isolated configuration leaf."
        />
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <UnifiedFilterConfigModal
            open
            onCancel={() => undefined}
            onConfirm={() => undefined}
            definitions={definitions}
            layoutItems={layoutItems}
            dataSources={dataSources}
          />
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/OpsAnalysis/UnifiedFilter/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1080, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
