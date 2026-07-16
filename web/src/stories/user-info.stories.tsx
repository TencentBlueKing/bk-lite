import type { Meta, StoryObj } from '@storybook/nextjs';

import UserInfo from '@/app/(core)/components/top-menu/user-info';

const meta: Meta<typeof UserInfo> = {
  component: UserInfo,
};

export default meta;

type Story = StoryObj<typeof UserInfo>;

export const Default: Story = {};
