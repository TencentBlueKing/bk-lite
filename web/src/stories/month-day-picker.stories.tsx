import type { Meta, StoryObj } from '@storybook/nextjs';
import MonthDayPicker from '@/app/opspilot/components/chatflow/components/MonthDayPicker';

const meta: Meta<typeof MonthDayPicker> = {
  component: MonthDayPicker,
  title: 'OpsPilot/MonthDayPicker',
  decorators: [
    (Story) => (
      <div style={{ padding: 16, background: '#fff' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof MonthDayPicker>;

export const Default: Story = {
  args: {
    value: 15,
  },
};

export const WarningDay: Story = {
  args: {
    value: 31,
  },
};

export const Disabled: Story = {
  args: {
    value: 7,
    disabled: true,
  },
};
