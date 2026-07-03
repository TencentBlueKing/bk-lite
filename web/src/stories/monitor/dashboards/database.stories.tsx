import type { Meta, StoryObj } from '@storybook/nextjs';
import { usePathname, useSearchParams } from '@storybook/nextjs/navigation.mock';
import ElasticsearchDashboard from '@/app/monitor/dashboards/objects/elasticsearch';
import MongodbDashboard from '@/app/monitor/dashboards/objects/mongodb';
import MssqlDashboard from '@/app/monitor/dashboards/objects/mssql';
import MysqlDashboard from '@/app/monitor/dashboards/objects/mysql';
import PostgresqlDashboard from '@/app/monitor/dashboards/objects/postgresql';
import RedisDashboard from '@/app/monitor/dashboards/objects/redis';

interface DashboardStoryArgs {
  dashboardKey: string;
  objectName: string;
  objectDisplayName: string;
  instanceId: string;
  instanceName: string;
  component: React.ComponentType;
}

const setDashboardQuery = (args: DashboardStoryArgs) => {
  const params = new URLSearchParams({
    monitorObjId: args.dashboardKey,
    name: args.objectName,
    monitorObjDisplayName: args.objectDisplayName,
    instance_id: args.instanceId,
    instance_name: args.instanceName,
    instance_id_keys: 'instance_id'
  });

  usePathname.mockImplementation(() => `/monitor/view/dashboard/${args.dashboardKey}`);
  useSearchParams.mockImplementation(() => params as ReturnType<typeof useSearchParams>);
  if (typeof window === 'undefined') return;
  window.history.replaceState(null, '', `/monitor/view/dashboard/${args.dashboardKey}?${params.toString()}`);
};

const DashboardFrame = (args: DashboardStoryArgs) => {
  setDashboardQuery(args);
  const Component = args.component;
  return <Component key={`${args.dashboardKey}-${args.instanceId}`} />;
};

const meta: Meta<typeof DashboardFrame> = {
  title: 'Monitor/Dashboard/Database',
  component: DashboardFrame,
  parameters: {
    layout: 'fullscreen'
  },
  args: {
    dashboardKey: 'mysql',
    objectName: 'Mysql',
    objectDisplayName: 'MySQL',
    instanceId: 'mysql-primary',
    instanceName: 'mysql-primary',
    component: MysqlDashboard
  }
};

export default meta;

type Story = StoryObj<typeof DashboardFrame>;

export const MySQL: Story = {
  args: {
    dashboardKey: 'mysql',
    objectName: 'Mysql',
    objectDisplayName: 'MySQL',
    instanceId: 'mysql-primary',
    instanceName: 'mysql-primary',
    component: MysqlDashboard
  }
};

export const Redis: Story = {
  args: {
    dashboardKey: 'redis',
    objectName: 'Redis',
    objectDisplayName: 'Redis',
    instanceId: 'redis-cache',
    instanceName: 'redis-cache',
    component: RedisDashboard
  }
};

export const MongoDB: Story = {
  args: {
    dashboardKey: 'mongodb',
    objectName: 'Mongodb',
    objectDisplayName: 'MongoDB',
    instanceId: 'mongodb-rs0',
    instanceName: 'mongodb-rs0',
    component: MongodbDashboard
  }
};

export const MSSQL: Story = {
  args: {
    dashboardKey: 'mssql',
    objectName: 'MSSQL',
    objectDisplayName: 'MSSQL',
    instanceId: 'mssql-main',
    instanceName: 'mssql-main',
    component: MssqlDashboard
  }
};

export const PostgreSQL: Story = {
  args: {
    dashboardKey: 'postgres',
    objectName: 'Postgres',
    objectDisplayName: 'PostgreSQL',
    instanceId: 'postgres-primary',
    instanceName: 'postgres-primary',
    component: PostgresqlDashboard
  }
};

export const Elasticsearch: Story = {
  args: {
    dashboardKey: 'elasticsearch',
    objectName: 'ElasticSearch',
    objectDisplayName: 'Elasticsearch',
    instanceId: 'es-cluster',
    instanceName: 'es-cluster',
    component: ElasticsearchDashboard
  }
};
