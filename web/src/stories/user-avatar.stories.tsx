import type { Meta, StoryObj } from '@storybook/react';
import UserAvatar from '@/components/user-avatar';

const meta: Meta<typeof UserAvatar> = {
  component: UserAvatar,
  title: 'Components/UserAvatar',
};

export default meta;

type Story = StoryObj<typeof UserAvatar>;

export const Default: Story = {
  args: {
    userName: 'admin',
  },
};

export const LongName: Story = {
  args: {
    userName: 'alexander.hamilton',
  },
};

export const Small: Story = {
  args: {
    userName: 'test',
    size: 'small',
  },
};
