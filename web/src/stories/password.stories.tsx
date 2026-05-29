import type { Meta, StoryObj } from '@storybook/react';
import Password from '@/components/password';

const meta: Meta<typeof Password> = {
  component: Password,
  title: 'Components/Password',
};

export default meta;

type Story = StoryObj<typeof Password>;

export const Default: Story = {
  args: {
    value: 'my-secret-password',
    placeholder: 'Enter password',
  },
};

export const WithCopy: Story = {
  args: {
    value: 'copy-this-token-abc123',
    allowCopy: true,
  },
};

export const DirectEdit: Story = {
  args: {
    value: '',
    clickToEdit: false,
    placeholder: 'Type password directly',
  },
};

export const Disabled: Story = {
  args: {
    value: 'cannot-edit',
    disabled: true,
  },
};
