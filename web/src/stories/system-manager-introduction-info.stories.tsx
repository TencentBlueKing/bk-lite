import type { Meta, StoryObj } from '@storybook/nextjs';
import IntroductionInfo from '@/app/system-manager/components/introduction-info';

const meta = {
  title: 'System Manager/IntroductionInfo',
  component: IntroductionInfo,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 720, padding: 16, background: 'var(--color-fill-1)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof IntroductionInfo>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    title: 'Application Management',
    message: 'Configure applications, menus, roles, and data permissions for console users.',
  },
};

export const LongMessage: Story = {
  args: {
    title: 'Security Settings',
    message: 'Manage authentication sources, login rules, password policies, and operation audit records.',
  },
};
