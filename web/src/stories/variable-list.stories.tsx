import type { Meta, StoryObj } from '@storybook/nextjs';
import VariableList from '@/app/opspilot/components/tool/variableList';

const meta = {
  title: 'OpsPilot/VariableList',
  component: VariableList,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 720, padding: 16, background: 'var(--color-bg)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof VariableList>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    value: [
      { key: 'instance_id', type: 'text', isRequired: true },
      { key: 'timeout', type: 'number', isRequired: false },
      { key: 'token', type: 'password', isRequired: true },
    ],
    onChange: () => {},
  },
};

export const Empty: Story = {
  args: {
    value: [],
    onChange: () => {},
  },
};

export const Disabled: Story = {
  args: {
    ...Default.args,
    disabled: true,
  },
};
