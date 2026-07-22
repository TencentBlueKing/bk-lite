import type { Meta, StoryObj } from '@storybook/react';
import { Button, Card } from 'antd';
import StepWizardFlow, {
  type StepWizardFlowStep,
} from '@/components/step-wizard-flow';
import TreeSelectorPanel from '@/components/tree-selector-panel';

interface DemoState {
  name: string;
  completed: boolean;
}

const basicSteps: StepWizardFlowStep<DemoState>[] = [
  {
    title: 'Profile',
    content: ({ next }) => (
      <Card bordered={false}>
        <Button type="primary" onClick={() => next({ name: 'Cluster A', completed: false })}>
          Continue
        </Button>
      </Card>
    ),
  },
  {
    title: 'Install',
    content: ({ state, prev, next }) => (
      <Card bordered={false}>
        <div style={{ marginBottom: 16 }}>Current target: {state.name || 'Unnamed'}</div>
        <Button style={{ marginRight: 8 }} onClick={prev}>
          Back
        </Button>
        <Button type="primary" onClick={() => next((current) => ({ ...current, completed: true }))}>
          Finish
        </Button>
      </Card>
    ),
  },
  {
    title: 'Done',
    content: ({ state, reset }) => (
      <Card bordered={false}>
        <div style={{ marginBottom: 16 }}>
          {state.completed ? 'Wizard state persisted across steps.' : 'Not completed'}
        </div>
        <Button onClick={() => reset({ name: '', completed: false })}>Reset</Button>
      </Card>
    ),
  },
];

interface GuidedState {
  collectorClusterId: string;
  cloudRegionId: string;
}

const guidedSteps: StepWizardFlowStep<GuidedState>[] = [
  {
    title: 'Access Config',
    content: ({ next }) => (
      <Card bordered={false}>
        <div style={{ marginBottom: 16 }}>
          Simulate a form that saves successfully, then hands control back to the wizard.
        </div>
        <Button
          type="primary"
          onClick={() =>
            next({
              collectorClusterId: 'prod-cluster-1',
              cloudRegionId: 'cn-hangzhou',
            })
          }
        >
          Save and continue
        </Button>
      </Card>
    ),
  },
  {
    title: 'Collector Install',
    content: ({ state, prev, next }) => (
      <Card bordered={false}>
        <div style={{ marginBottom: 8 }}>
          Collector ID: {state.collectorClusterId || '--'}
        </div>
        <div style={{ marginBottom: 16 }}>
          Cloud region: {state.cloudRegionId || '--'}
        </div>
        <Button style={{ marginRight: 8 }} onClick={prev}>
          Back
        </Button>
        <Button type="primary" onClick={() => next()}>
          Verify and continue
        </Button>
      </Card>
    ),
  },
  {
    title: 'Access Complete',
    content: ({ state, reset }) => (
      <Card bordered={false}>
        <div style={{ marginBottom: 16 }}>
          Saved state stayed available across the full K8s setup flow for
          {` ${state.collectorClusterId || ' --'}`}.
        </div>
        <Button
          onClick={() =>
            reset({
              collectorClusterId: '',
              cloudRegionId: '',
            })
          }
        >
          Add another cluster
        </Button>
      </Card>
    ),
  },
];

const treeData = [
  {
    title: 'Compute',
    key: 'compute',
    children: [
      { title: 'Kubernetes', key: 'k8s', icon: 'cc-default_默认', count: 18, children: [] },
      { title: 'Virtual machine', key: 'vm', icon: 'cc-default_默认', count: 6, children: [] },
    ],
  },
  {
    title: 'Database',
    key: 'database',
    children: [
      { title: 'PostgreSQL cluster', key: 'pg', icon: 'cc-default_默认', count: 12, children: [] },
      { title: 'Redis cache', key: 'redis', icon: 'cc-default_默认', count: 4, children: [] },
    ],
  },
];

const treePanelData = [
  {
    title: 'All integrations',
    key: 'all',
    children: [],
  },
  ...treeData,
];

const NavigationFamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Step wizard flows
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <StepWizardFlow
              initialState={{
                name: '',
                completed: false,
              }}
              steps={basicSteps}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <StepWizardFlow
              initialState={{
                collectorClusterId: '',
                cloudRegionId: '',
              }}
              steps={guidedSteps}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Tree selector panels
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <TreeSelectorPanel
              data={treeData}
              defaultSelectedKey="k8s"
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <TreeSelectorPanel
              data={treePanelData}
              defaultSelectedKey="all"
              surface="panel"
              style={{ width: 236, height: 320 }}
              showAllMenu
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <TreeSelectorPanel
              data={treePanelData}
              defaultSelectedKey="all"
              draggable
              showAllMenu
              surface="panel"
              style={{ width: 236, height: 320 }}
              buildSortPayload={(nodes) =>
                nodes.map((item) => ({
                  type: String(item.key),
                  object_list: (item.children || []).map((child) => String(child.title)),
                }))
              }
            />
          </div>
        </div>
      </section>

      <section className="space-y-2 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Storybook structure
        </div>
        <div className="text-sm text-[var(--color-text-2)]">
          The Navigation family is governed through step-wizard and tree-selector sub-contracts instead of separate navigation leaf stories.
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Framework/Navigation/FamilyOverview',
  component: NavigationFamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1120, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof NavigationFamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
