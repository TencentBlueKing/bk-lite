import type { Meta, StoryObj } from '@storybook/nextjs';
import ToolCallGroup from '@/app/opspilot/components/custom-chat-sse/ToolCallGroup';

const meta: Meta<typeof ToolCallGroup> = {
  component: ToolCallGroup,
  title: 'OpsPilot/ToolCallGroup',
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 720, padding: 16, background: '#fff' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof ToolCallGroup>;

const completedToolCalls = [
  {
    id: '1',
    name: 'search_workload_across_namespaces',
    args: JSON.stringify({ query: 'nginx', cluster: 'prod-cluster' }),
    status: 'completed' as const,
    result: 'Found 2 workloads in namespace default.',
  },
  {
    id: '2',
    name: 'analyze_deployment_configurations',
    args: JSON.stringify({ namespace: 'default', workloads: ['nginx-web'] }),
    status: 'completed' as const,
    result: 'Detected missing resource limits and missing readiness probe.',
  },
  {
    id: '3',
    name: 'request_user_choice',
    args: JSON.stringify({ title: 'Choose a repair mode', options: ['full_fix', 'by_category'] }),
    status: 'completed' as const,
    result: '用户回答: full_fix。',
  },
];

export const Completed: Story = {
  args: {
    toolCalls: completedToolCalls,
    isStreaming: false,
  },
};

export const Streaming: Story = {
  args: {
    toolCalls: [
      ...completedToolCalls.slice(0, 2),
      {
        id: '4',
        name: 'generate_fix_patch',
        args: JSON.stringify({ workload: 'nginx-web', scope: 'all' }),
        status: 'calling',
        result: '',
      },
    ],
    isStreaming: true,
  },
};

export const MinimalArgs: Story = {
  args: {
    toolCalls: [
      {
        id: '1',
        name: 'report_intent',
        args: '{}',
        status: 'completed',
        result: 'Intent updated to "Scanning workloads".',
      },
    ],
    isStreaming: false,
  },
};
