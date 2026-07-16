import type { Meta, StoryObj } from '@storybook/react';
import React, { useState } from 'react';
import { Form } from 'antd';
import OpsAnalysisDataSourceParamsConfig from '@/components/ops-analysis-data-source-params-config';
import OpsAnalysisDataSourceSelect from '@/components/ops-analysis-data-source-select';
import SectionHeader from '@/components/section-header';
import type { DatasourceItem } from '@/components/ops-analysis-widgets';

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
        filterType: 'params',
        required: true,
        value: '',
      },
      {
        name: 'instance_limit',
        alias_name: 'Instance Limit',
        type: 'number',
        filterType: 'params',
        value: 20,
      },
      {
        name: 'time_range',
        alias_name: 'Time Range',
        type: 'timeRange',
        filterType: 'filter',
        value: 10080,
      },
      {
        name: 'env',
        alias_name: 'Environment',
        type: 'string',
        filterType: 'fixed',
        value: 'prod',
        options: [
          { label: 'Production', value: 'prod' },
          { label: 'Staging', value: 'staging' },
        ],
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

const DataSourceFamilyOverview = () => {
  const [value, setValue] = useState<number | undefined>(1);

  const selectedDataSource = dataSources.find((item) => item.id === value) || dataSources[0];

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Data source select contract"
          titleClassName="text-sm font-semibold"
          description="Permission-aware datasource option rendering and searchable datasource switching belong to the same ops-analysis query configuration contract."
        />
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <OpsAnalysisDataSourceSelect
              value={value}
              dataSources={dataSources}
              placeholder="Select data source"
              showSearch
              onChange={setValue}
            />
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <OpsAnalysisDataSourceSelect
              value={value}
              dataSources={dataSources}
              placeholder="Select data source"
              showSearch
              disabled
              onChange={() => undefined}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Params config contract"
          titleClassName="text-sm font-semibold"
          description="Generated parameter fields, fixed values, readonly states, and time-range inputs stay governed beside datasource selection instead of living in a separate Storybook root."
        />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <Form labelCol={{ span: 5 }} layout="horizontal">
              <OpsAnalysisDataSourceParamsConfig
                selectedDataSource={selectedDataSource}
                includeFilterTypes={['params', 'fixed', 'filter']}
              />
            </Form>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <Form labelCol={{ span: 5 }} layout="horizontal">
              <OpsAnalysisDataSourceParamsConfig
                selectedDataSource={selectedDataSource}
                readonly
                includeFilterTypes={['params', 'fixed', 'filter']}
              />
            </Form>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Combined query configuration flow"
          titleClassName="text-sm font-semibold"
          description="Real ops-analysis pages compose datasource selection and parameter rendering together before handing off to widget-specific display settings."
        />
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <Form labelCol={{ span: 5 }} layout="horizontal">
            <Form.Item label="Data source" required>
              <OpsAnalysisDataSourceSelect
                value={value}
                dataSources={dataSources}
                placeholder="Select data source"
                showSearch
                onChange={setValue}
              />
            </Form.Item>
            <OpsAnalysisDataSourceParamsConfig
              selectedDataSource={selectedDataSource}
              includeFilterTypes={['params', 'fixed']}
            />
          </Form>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/OpsAnalysis/DataSource/FamilyOverview',
  component: DataSourceFamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1080, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof DataSourceFamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
