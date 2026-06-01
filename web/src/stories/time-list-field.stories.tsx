import type { Meta, StoryObj } from '@storybook/nextjs';
import TimeListField from '@/app/opspilot/components/chatflow/components/TimeListField';

const meta: Meta<typeof TimeListField> = {
  component: TimeListField,
  title: 'OpsPilot/TimeListField',
  decorators: [
    (Story) => (
      <div style={{ width: 360, padding: 16, background: '#fff' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof TimeListField>;

export const SingleTime: Story = {
  args: {
    value: ['09:00'],
    min: 1,
  },
};

export const MultipleTimes: Story = {
  args: {
    value: ['09:00', '13:30', '18:00'],
    min: 1,
    max: 4,
  },
};

export const Disabled: Story = {
  args: {
    value: ['08:30', '20:00'],
    disabled: true,
  },
};
