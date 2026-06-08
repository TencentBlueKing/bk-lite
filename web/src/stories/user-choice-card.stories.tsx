import type { Meta, StoryObj } from '@storybook/nextjs';
import UserChoiceCard from '@/app/opspilot/components/custom-chat-sse/UserChoiceCard';

const meta: Meta<typeof UserChoiceCard> = {
  component: UserChoiceCard,
  title: 'OpsPilot/UserChoiceCard',
  decorators: [
    (Story) => (
      <div style={{ padding: 16, background: '#fff' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof UserChoiceCard>;

const baseRequest = {
  execution_id: 'exec-choice-1',
  node_id: 'node-choice-1',
  choice_id: 'choice-1',
  title: 'Choose a repair strategy',
  description: 'Select a fix mode or enter your own custom instruction.',
  timeout_seconds: 180,
  received_at: Date.now(),
  status: 'pending' as const,
  selected: [],
};

export const ButtonMode: Story = {
  args: {
    token: 'mock-token',
    onSubmit: () => {},
    request: {
      ...baseRequest,
      options: [
        { key: 'full_fix', label: 'Full Fix', description: 'Patch all issues in one go.', recommended: true, icon: '🚀' },
        { key: 'by_category', label: 'By Category', description: 'Fix security, probes, and resources separately.', icon: '🗂️' },
        { key: 'by_workload', label: 'By Workload', description: 'Review and patch one workload at a time.', icon: '📦' },
      ],
      multiple: false,
      min_select: 1,
      max_select: 1,
      default_keys: ['full_fix'],
      display_hint: 'buttons' as const,
    },
  },
};

export const CheckboxMode: Story = {
  args: {
    token: 'mock-token',
    onSubmit: () => {},
    request: {
      ...baseRequest,
      choice_id: 'choice-2',
      title: 'Select the issue categories to fix',
      options: [
        { key: 'security', label: 'Security Context', description: 'runAsNonRoot, capabilities, readonly FS' },
        { key: 'resources', label: 'Resources', description: 'requests and limits' },
        { key: 'probes', label: 'Health Probes', description: 'liveness and readiness probe settings', recommended: true },
      ],
      multiple: true,
      min_select: 1,
      max_select: 2,
      default_keys: ['probes'],
      display_hint: 'checkbox' as const,
    },
  },
};

export const DropdownMode: Story = {
  args: {
    token: 'mock-token',
    onSubmit: () => {},
    request: {
      ...baseRequest,
      choice_id: 'choice-3',
      title: 'Choose the target environment',
      options: Array.from({ length: 10 }, (_, index) => ({
        key: `cluster-${index + 1}`,
        label: `Cluster ${index + 1}`,
        description: `Environment ${index + 1}`,
      })),
      multiple: false,
      min_select: 1,
      max_select: 1,
      default_keys: [],
      display_hint: 'auto' as const,
    },
  },
};

export const TextMode: Story = {
  args: {
    token: 'mock-token',
    onSubmit: () => {},
    request: {
      ...baseRequest,
      choice_id: 'choice-4',
      title: 'Provide a custom repair instruction',
      description: 'Describe how you want the generated fix to be constrained.',
      options: [],
      multiple: false,
      min_select: 1,
      max_select: 1,
      default_keys: [],
      display_hint: 'text' as const,
    },
  },
};
