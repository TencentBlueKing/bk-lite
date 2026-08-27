import type { Meta, StoryObj } from '@storybook/nextjs';
import { usePathname, useSearchParams } from '@storybook/nextjs/navigation.mock';
import NetflowDashboard from '@/app/monitor/dashboards/objects/netflow';
import SflowDashboard from '@/app/monitor/dashboards/objects/sflow';

interface DashboardStoryArgs {
  dashboardKey: string;
  monitorObjId: string;
  objectName: string;
  objectDisplayName: string;
  instanceId: string;
  instanceName: string;
  component: React.ComponentType;
}

const setDashboardQuery = (args: DashboardStoryArgs) => {
  const params = new URLSearchParams({
    monitorObjId: args.monitorObjId,
    name: args.objectName,
    monitorObjDisplayName: args.objectDisplayName,
    instance_id: args.instanceId,
    instance_name: args.instanceName,
    instance_id_values: args.instanceId,
    instance_id_keys: 'instance_id',
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
  title: 'Monitor/Dashboard/Network Flow',
  component: DashboardFrame,
  parameters: {
    layout: 'fullscreen',
  },
  args: {
    dashboardKey: 'netflow',
    monitorObjId: 'switch',
    objectName: 'Switch',
    objectDisplayName: '交换机',
    instanceId: 'flow-switch-1',
    instanceName: 'NetFlow-Switch-1',
    component: NetflowDashboard,
  },
};

export default meta;

type Story = StoryObj<typeof DashboardFrame>;

export const NetFlow: Story = {
  args: {
    dashboardKey: 'netflow',
    monitorObjId: 'switch',
    objectName: 'Switch',
    objectDisplayName: '交换机',
    instanceId: 'flow-switch-1',
    instanceName: 'NetFlow-Switch-1',
    component: NetflowDashboard,
  },
};

export const SFlow: Story = {
  args: {
    dashboardKey: 'sflow',
    monitorObjId: 'switch',
    objectName: 'Switch',
    objectDisplayName: '交换机',
    instanceId: 'flow-switch-1',
    instanceName: 'sFlow-Switch-1',
    component: SflowDashboard,
  },
};
