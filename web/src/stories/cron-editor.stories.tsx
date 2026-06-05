import type { Meta, StoryObj } from '@storybook/nextjs';
import CronEditor from '@/app/opspilot/components/chatflow/components/CronEditor';

const meta: Meta<typeof CronEditor> = {
  component: CronEditor,
  title: 'OpsPilot/CronEditor',
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 620, padding: 16, background: '#fff' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof CronEditor>;

export const Default: Story = {
  args: {
    value: '0 9 * * 1-5',
  },
};

export const DailyAtNoon: Story = {
  args: {
    value: '0 12 * * *',
  },
};

export const Disabled: Story = {
  args: {
    value: '30 2 1 * *',
    disabled: true,
  },
};
