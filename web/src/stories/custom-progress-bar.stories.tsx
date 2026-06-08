import type { Meta, StoryObj } from '@storybook/nextjs';
import CustomProgressBar from '@/app/opspilot/(pages)/settings/quota/customProgressBar';

const meta: Meta<typeof CustomProgressBar> = {
  component: CustomProgressBar,
  title: 'OpsPilot/CustomProgressBar',
  decorators: [
    (Story) => (
      <div style={{ width: 720, padding: 16, background: '#fff' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof CustomProgressBar>;

export const WithinLimit: Story = {
  args: {
    label: 'Knowledge Files',
    usage: 42,
    total: 100,
    unit: 'GB',
  },
};

export const NearlyFull: Story = {
  args: {
    label: 'Daily Token Usage',
    usage: 94,
    total: 100,
    unit: '%',
  },
};

export const OverLimit: Story = {
  args: {
    label: 'Custom Bots',
    usage: 14,
    total: 10,
    unit: '',
  },
};
