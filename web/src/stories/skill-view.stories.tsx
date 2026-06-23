import type { Meta, StoryObj } from '@storybook/nextjs';
import SkillView from '@/app/opspilot/components/custom-chat-sse/SkillView';

const meta: Meta<typeof SkillView> = {
  component: SkillView,
  title: 'OpsPilot/SkillView',
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 720, padding: 16, background: '#fff' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof SkillView>;

export const MatchedPackages: Story = {
  args: {
    items: [
      {
        id: 'kubernetes-specialist',
        name: 'Kubernetes Specialist',
        package_id: 'kubernetes-specialist',
        description: 'Kubernetes workload troubleshooting',
        missing_tools: [],
      },
    ],
  },
};

export const MissingTools: Story = {
  args: {
    items: [
      {
        id: 'agent-browser',
        name: 'agent-browser',
        package_id: 'agent-browser',
        description: 'Browser automation workflow',
        missing_tools: ['agent_browser'],
      },
    ],
  },
};
