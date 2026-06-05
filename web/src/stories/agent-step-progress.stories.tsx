import type { Meta, StoryObj } from '@storybook/nextjs';
import AgentStepProgress from '@/app/opspilot/components/custom-chat-sse/AgentStepProgress';

const meta: Meta<typeof AgentStepProgress> = {
  component: AgentStepProgress,
  title: 'OpsPilot/AgentStepProgress',
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 720, padding: 16, background: '#fff' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof AgentStepProgress>;

export const RunningAgents: Story = {
  args: {
    steps: [
      {
        agent_name: 'main',
        step: 2,
        max_steps: 5,
        status: 'running',
        description: 'Analyzing deployment manifests',
        tool_name: 'analyze_deployment_configurations',
        total_elapsed_seconds: 8.4,
      },
      {
        agent_name: 'browser',
        step: 1,
        max_steps: 3,
        status: 'parallel_started',
        description: 'Collecting UI screenshots for comparison',
        total_elapsed_seconds: 1.8,
      },
    ],
  },
};

export const CompletedAgents: Story = {
  args: {
    steps: [
      {
        agent_name: 'main',
        step: 4,
        max_steps: 4,
        status: 'completed',
        description: 'Generated fix summary',
        tool_name: 'request_user_choice',
        total_elapsed_seconds: 12.3,
      },
      {
        agent_name: 'k8s-auditor',
        step: 3,
        max_steps: 3,
        status: 'parallel_completed',
        description: 'Checked security context and probes',
        tool_name: 'scan_cluster_workloads',
        total_elapsed_seconds: 9.6,
      },
    ],
  },
};

export const ErrorState: Story = {
  args: {
    steps: [
      {
        agent_name: 'main',
        step: 2,
        max_steps: 4,
        status: 'error',
        description: 'Failed to fetch workload details from cluster',
        tool_name: 'get_workload_details',
        total_elapsed_seconds: 3.2,
      },
    ],
  },
};
