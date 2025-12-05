import type { Meta, StoryObj } from '@storybook/react';
import TopMenu from '@/components/top-menu';

const meta: Meta<typeof TopMenu> = {
  component: TopMenu,
};

export default meta;

type Story = StoryObj<typeof TopMenu>;

export const Default: Story = {
  args: {
    hideMainMenu: false,
  },
};

export const HideMainMenu: Story = {
  args: {
    hideMainMenu: true,
  },
};