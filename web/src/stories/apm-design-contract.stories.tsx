import type { Meta, StoryObj } from '@storybook/nextjs';
import { SearchOutlined } from '@ant-design/icons';
import { Button, Input, Tag, Typography, type TableColumnsType } from 'antd';
import ApplicationCard from '@/app/apm/components/application-card';
import ApmDataTable from '@/app/apm/components/apm-data-table';
import ApmRouteShell, { ApmSurface } from '@/app/apm/components/apm-route-shell';
import CatalogState from '@/app/apm/components/catalog-state';
import FilterToolbar from '@/components/filter-toolbar';

const meta = {
  title: 'APM/Design Contract',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const RouteAndSurfaceHierarchy: Story = {
  name: '紧凑页面壳与承载面',
  render: () => (
    <ApmRouteShell
      title="服务"
      description="统一使用 16 / 14 / 12 字号、透明页面画布与单层内容承载面。"
      dependency="telemetry"
    >
      <ApmSurface>
        <div className="text-sm text-[var(--color-text-2)]">
          二级导航已表达当前页面，页面壳不再重复渲染介绍卡；筛选、表格和业务卡片直接进入内容工作面。
        </div>
      </ApmSurface>
    </ApmRouteShell>
  ),
};

export const CatalogStateMatrix: Story = {
  name: '数据状态矩阵',
  render: () => (
    <div className="grid gap-3 bg-[var(--color-background-body)] p-4 md:grid-cols-2">
      <ApmSurface><CatalogState kind="loading" compact /></ApmSurface>
      <ApmSurface>
        <CatalogState
          kind="empty"
          compact
          description="当前筛选范围暂无数据。"
          action={<Button type="primary">清除筛选</Button>}
        />
      </ApmSurface>
      <ApmSurface><CatalogState kind="error" compact onRetry={() => undefined} /></ApmSurface>
      <ApmSurface><CatalogState kind="degraded" compact onRetry={() => undefined} /></ApmSurface>
      <ApmSurface><CatalogState kind="forbidden" compact /></ApmSurface>
    </div>
  ),
};

const services = [
  { name: 'checkout-api', silent: false },
  { name: 'payment-service-with-a-very-long-production-name', silent: false },
  { name: 'legacy-worker', silent: true },
];

const manyServices = [
  ...services,
  { name: 'demo-inventory', silent: false },
  { name: 'demo-orders', silent: false },
  { name: 'demo-payment', silent: false },
  { name: 'demo-storefront', silent: false },
  { name: 'ingest-verify-django', silent: false },
];

export const ApplicationCardStates: Story = {
  name: '应用卡状态与长文本',
  render: () => (
    <div className="grid grid-cols-1 gap-3 bg-[var(--color-background-body)] p-4 md:grid-cols-2">
      <ApplicationCard
        label="交易清结算 / production 🚦"
        status="critical"
        services={services}
        requestRate={1284.4}
        errorRate={0.023}
        requestRateTrend={[700, 860, 980, 1210, 1284]}
        errorRateTrend={[0.006, 0.01, 0.008, 0.017, 0.023]}
        metricUnavailable={false}
        alertCount={3}
        timeWindow="1h"
        servicesHref="/apm/services?perspective=service&namespace=checkout"
        eventsHref="/apm/events/alerts"
        href="/apm/integration/applications/checkout"
      />
      <ApplicationCard
        label="支付应用"
        status="normal"
        services={services}
        requestRate={null}
        errorRate={null}
        requestRateTrend={[]}
        errorRateTrend={[]}
        metricUnavailable
        alertCount={0}
        timeWindow="1h"
        servicesHref="/apm/services?perspective=service&namespace=payment"
        eventsHref="/apm/events/alerts"
        href="/apm/integration/applications/payment"
        onRetryMetrics={() => undefined}
      />
      <ApplicationCard
        label="本机 APM 演示商城"
        status="warning"
        services={manyServices}
        requestRate={6.5}
        errorRate={0.112}
        requestRateTrend={[4, 5, 6, 6.5]}
        errorRateTrend={[0.08, 0.09, 0.1, 0.112]}
        metricUnavailable={false}
        alertCount={1}
        timeWindow="1h"
        servicesHref="/apm/services?perspective=service&namespace=demo-shop"
        eventsHref="/apm/events/alerts"
        href="/apm/integration/applications/demo-shop"
      />
      <ApplicationCard
        label="bklite"
        status="normal"
        services={[{ name: 'bklite-server', silent: false }]}
        requestRate={0.00167}
        errorRate={0}
        requestRateTrend={[0.001, 0.0014, 0.00167]}
        errorRateTrend={[0, 0, 0]}
        metricUnavailable={false}
        alertCount={0}
        timeWindow="1h"
        servicesHref="/apm/services?perspective=service&namespace=bklite"
        eventsHref="/apm/events/alerts"
        href="/apm/integration/applications/bklite"
      />
    </div>
  ),
};

export const NarrowApplicationCard: Story = {
  name: '320px 窄屏应用卡',
  parameters: {
    viewport: { defaultViewport: 'mobile1' },
  },
  render: () => (
    <div className="w-[320px] max-w-full bg-[var(--color-background-body)] p-2">
      <ApplicationCard
        label="a-very-long-service-namespace-with-emoji-🚀"
        status="warning"
        services={services}
        requestRate={12.5}
        errorRate={0.001}
        requestRateTrend={[8, 10, 9, 12.5]}
        errorRateTrend={[0.002, 0.001, 0.0015, 0.001]}
        metricUnavailable={false}
        alertCount={0}
        timeWindow="15m"
        servicesHref="/apm/services?perspective=service&namespace=checkout"
        eventsHref="/apm/events/alerts"
        href="/apm/integration/applications/long-name"
      />
    </div>
  ),
};

interface TableContractRow {
  id: number;
  name: string;
  service: string;
  status: string;
  throughput: string;
}

const tableColumns: TableColumnsType<TableContractRow> = [
  { title: '名称', dataIndex: 'name' },
  { title: '服务', dataIndex: 'service', responsive: ['sm'] },
  {
    title: '吞吐量',
    dataIndex: 'throughput',
    width: 120,
    align: 'right',
    responsive: ['md'],
    className: 'tabular-nums',
  },
  {
    title: '状态',
    dataIndex: 'status',
    width: 88,
    align: 'center',
    render: (value) => <Tag bordered={false} color="success">{value}</Tag>,
  },
];

const tableRows: TableContractRow[] = [
  { id: 1, name: 'checkout-api-production-with-long-name', service: 'checkout', status: '正常', throughput: '1,284.4/s' },
  { id: 2, name: 'payment-worker', service: 'payment', status: '正常', throughput: '862.1/s' },
];

export const DataTableDensityAndResponsive: Story = {
  name: '列表 16px 内沿与紧凑行高',
  render: () => (
    <div className="grid gap-4 bg-[var(--color-background-body)] p-4 lg:grid-cols-[minmax(0,1fr)_360px]">
      <ApmSurface>
        <div className="flex flex-col gap-4">
          <FilterToolbar align="start" spacing="flush" className="w-full" contentClassName="w-full">
            <Input allowClear className="min-w-0 flex-1" prefix={<SearchOutlined aria-hidden="true" />} placeholder="搜索服务" />
            <Typography.Text type="secondary" className="text-xs">共 42 条</Typography.Text>
          </FilterToolbar>
          <ApmDataTable<TableContractRow>
            columns={tableColumns}
            dataSource={tableRows}
            pagination={{ current: 1, pageSize: 20, total: 42 }}
            rowKey="id"
          />
        </div>
      </ApmSurface>
      <ApmSurface>
        <ApmDataTable<TableContractRow>
          columns={tableColumns}
          dataSource={tableRows}
          pagination={false}
          rowKey="id"
        />
      </ApmSurface>
    </div>
  ),
};
