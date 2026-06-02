import type { Meta, StoryObj } from '@storybook/nextjs';
import ApprovalCard from '@/app/opspilot/components/custom-chat-sse/ApprovalCard';

const meta: Meta<typeof ApprovalCard> = {
  component: ApprovalCard,
  title: 'OpsPilot/ApprovalCard',
  decorators: [
    (Story) => (
      <div style={{ padding: 16, background: '#fff' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof ApprovalCard>;

const now = Date.now();

export const Pending: Story = {
  args: {
    token: 'mock-token',
    onDecision: () => {},
    request: {
      execution_id: 'exec-1',
      node_id: 'node-1',
      tool_call_id: 'tool-1',
      tool_name: 'apply_kubernetes_fix',
      tool_args: {
        cluster: 'prod-cluster',
        namespace: 'default',
        workload: 'nginx-web',
      },
      timeout_seconds: 300,
      received_at: now,
      status: 'pending',
    },
  },
};

export const Approved: Story = {
  args: {
    token: 'mock-token',
    onDecision: () => {},
    request: {
      execution_id: 'exec-2',
      node_id: 'node-2',
      tool_call_id: 'tool-2',
      tool_name: 'delete_pod',
      tool_args: {
        namespace: 'ops',
        pod_name: 'worker-0',
      },
      timeout_seconds: 300,
      received_at: now - 30_000,
      status: 'approved',
    },
  },
};

export const Rejected: Story = {
  args: {
    token: 'mock-token',
    onDecision: () => {},
    request: {
      execution_id: 'exec-3',
      node_id: 'node-3',
      tool_call_id: 'tool-3',
      tool_name: 'patch_deployment_image',
      tool_args: {
        namespace: 'prod',
        workload: 'api-server',
        image: 'example.com/api:v2',
      },
      timeout_seconds: 120,
      received_at: now - 45_000,
      status: 'rejected',
    },
  },
};

export const TimedOut: Story = {
  args: {
    token: 'mock-token',
    onDecision: () => {},
    request: {
      execution_id: 'exec-4',
      node_id: 'node-4',
      tool_call_id: 'tool-4',
      tool_name: 'restart_statefulset',
      tool_args: {
        namespace: 'monitor',
        workload: 'prometheus',
      },
      timeout_seconds: 10,
      received_at: now - 20_000,
      status: 'pending',
    },
  },
};
