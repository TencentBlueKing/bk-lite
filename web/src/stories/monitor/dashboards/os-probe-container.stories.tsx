import type { Meta, StoryObj } from '@storybook/nextjs';
import { usePathname, useSearchParams } from '@storybook/nextjs/navigation.mock';
import HostDashboard from '@/app/monitor/dashboards/objects/host';
import WebsiteDashboard from '@/app/monitor/dashboards/objects/website';
import PingDashboard from '@/app/monitor/dashboards/objects/ping';
import TcpDashboard from '@/app/monitor/dashboards/objects/tcp';
import K8sClusterDashboard from '@/app/monitor/dashboards/objects/k8s-cluster';
import K8sNodeDashboard from '@/app/monitor/dashboards/objects/k8s-node';
import K8sPodDashboard from '@/app/monitor/dashboards/objects/k8s-pod';

interface DashboardStoryArgs {
  dashboardKey: string;
  objectName: string;
  objectDisplayName: string;
  instanceId: string;
  instanceName: string;
  instanceIdKeys?: string;
  instanceIdValues?: string;
  component: React.ComponentType;
}

const setDashboardQuery = (args: DashboardStoryArgs) => {
  const params = new URLSearchParams({
    monitorObjId: args.dashboardKey,
    name: args.objectName,
    monitorObjDisplayName: args.objectDisplayName,
    instance_id: args.instanceId,
    instance_name: args.instanceName,
    instance_id_keys: args.instanceIdKeys || 'instance_id'
  });
  if (args.instanceIdValues) {
    params.set('instance_id_values', args.instanceIdValues);
  }
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
  title: 'Monitor/Dashboard/OS Probe Container',
  component: DashboardFrame,
  parameters: {
    layout: 'fullscreen'
  },
  args: {
    dashboardKey: 'host',
    objectName: 'Host',
    objectDisplayName: '主机',
    instanceId: 'mac',
    instanceName: 'mac',
    component: HostDashboard
  }
};

export default meta;

type Story = StoryObj<typeof DashboardFrame>;

export const Host: Story = {
  args: {
    dashboardKey: 'host',
    objectName: 'Host',
    objectDisplayName: '主机',
    instanceId: 'mac',
    instanceName: 'mac',
    component: HostDashboard
  }
};

export const Website: Story = {
  args: {
    dashboardKey: 'website',
    objectName: 'Website',
    objectDisplayName: '网站',
    instanceId: 'blueking-lite',
    instanceName: 'BlueKing Lite',
    component: WebsiteDashboard
  }
};

export const Ping: Story = {
  args: {
    dashboardKey: 'ping',
    objectName: 'Ping',
    objectDisplayName: 'Ping',
    instanceId: 'local-ping',
    instanceName: '127.0.0.1',
    component: PingDashboard
  }
};

export const TCP: Story = {
  args: {
    dashboardKey: 'tcp',
    objectName: 'TCPPort',
    objectDisplayName: 'TCP',
    instanceId: 'local-tcp',
    instanceName: '127.0.0.1:3000',
    component: TcpDashboard
  }
};

export const K8sCluster: Story = {
  name: 'K8s Cluster',
  args: {
    dashboardKey: 'k8s-cluster',
    objectName: 'Cluster',
    objectDisplayName: '集群',
    instanceId: 'orbstack',
    instanceName: 'orbstack',
    component: K8sClusterDashboard
  }
};

export const K8sNode: Story = {
  name: 'K8s Node',
  args: {
    dashboardKey: 'k8s-node',
    objectName: 'Node',
    objectDisplayName: '节点',
    instanceId: 'orb-node-1',
    instanceName: 'orb-node-1',
    instanceIdKeys: 'cluster,node',
    instanceIdValues: 'orbstack,orb-node-1',
    component: K8sNodeDashboard
  }
};

export const K8sPod: Story = {
  name: 'K8s Pod',
  args: {
    dashboardKey: 'k8s-pod',
    objectName: 'Pod',
    objectDisplayName: 'Pod',
    instanceId: 'demo-pod-1',
    instanceName: 'demo-pod-1',
    instanceIdKeys: 'cluster,pod',
    instanceIdValues: 'orbstack,demo-pod-1',
    component: K8sPodDashboard
  }
};
