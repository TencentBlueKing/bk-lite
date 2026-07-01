import type { Meta, StoryObj } from '@storybook/nextjs';
import { usePathname, useSearchParams } from '@storybook/nextjs/navigation.mock';
import ActiveMQDashboard from '@/app/monitor/dashboards/objects/activemq';
import ApacheDashboard from '@/app/monitor/dashboards/objects/apache';
import ConsulDashboard from '@/app/monitor/dashboards/objects/consul';
import DockerDashboard from '@/app/monitor/dashboards/objects/docker';
import IBMMQDashboard from '@/app/monitor/dashboards/objects/ibmmq';
import NginxDashboard from '@/app/monitor/dashboards/objects/nginx';
import RabbitMQDashboard from '@/app/monitor/dashboards/objects/rabbitmq';
import TomcatDashboard from '@/app/monitor/dashboards/objects/tomcat';
import ZookeeperDashboard from '@/app/monitor/dashboards/objects/zookeeper';

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
  title: 'Monitor/Dashboard/Middleware',
  component: DashboardFrame,
  parameters: {
    layout: 'fullscreen'
  },
  args: {
    dashboardKey: 'nginx',
    objectName: 'nginx',
    objectDisplayName: 'Nginx',
    instanceId: 'nginx-edge',
    instanceName: 'nginx-edge',
    component: NginxDashboard
  }
};

export default meta;

type Story = StoryObj<typeof DashboardFrame>;

export const Nginx: Story = {
  args: {
    dashboardKey: 'nginx',
    objectName: 'nginx',
    objectDisplayName: 'Nginx',
    instanceId: 'nginx-edge',
    instanceName: 'nginx-edge',
    component: NginxDashboard
  }
};

export const Docker: Story = {
  args: {
    dashboardKey: 'docker',
    objectName: 'Docker',
    objectDisplayName: 'Docker',
    instanceId: 'docker-local',
    instanceName: 'docker-local',
    component: DockerDashboard
  }
};

export const ActiveMQ: Story = {
  args: {
    dashboardKey: 'activemq',
    objectName: 'ActiveMQ',
    objectDisplayName: 'ActiveMQ',
    instanceId: 'activemq-main',
    instanceName: 'activemq-main',
    component: ActiveMQDashboard
  }
};

export const Apache: Story = {
  args: {
    dashboardKey: 'apache',
    objectName: 'Apache',
    objectDisplayName: 'Apache',
    instanceId: 'apache-web',
    instanceName: 'apache-web',
    component: ApacheDashboard
  }
};

export const Consul: Story = {
  args: {
    dashboardKey: 'consul',
    objectName: 'Consul',
    objectDisplayName: 'Consul',
    instanceId: 'consul-server',
    instanceName: 'consul-server',
    component: ConsulDashboard
  }
};

export const RabbitMQ: Story = {
  args: {
    dashboardKey: 'rabbitmq',
    objectName: 'RabbitMQ',
    objectDisplayName: 'RabbitMQ',
    instanceId: 'rabbitmq-main',
    instanceName: 'rabbitmq-main',
    component: RabbitMQDashboard
  }
};

export const IBMMQ: Story = {
  name: 'IBM MQ',
  args: {
    dashboardKey: 'ibmmq',
    objectName: 'IBMMQ',
    objectDisplayName: 'IBM MQ',
    instanceId: 'ibmmq-qm1',
    instanceName: 'ibmmq-qm1',
    component: IBMMQDashboard
  }
};

export const Tomcat: Story = {
  args: {
    dashboardKey: 'tomcat',
    objectName: 'Tomcat',
    objectDisplayName: 'Tomcat',
    instanceId: 'tomcat-app',
    instanceName: 'tomcat-app',
    component: TomcatDashboard
  }
};

export const Zookeeper: Story = {
  args: {
    dashboardKey: 'zookeeper',
    objectName: 'Zookeeper',
    objectDisplayName: 'Zookeeper',
    instanceId: 'zookeeper-main',
    instanceName: 'zookeeper-main',
    component: ZookeeperDashboard
  }
};
