import type { Meta, StoryObj } from '@storybook/nextjs';
import ThemeSwitcher from '@/app/(core)/components/top-menu/user-info/themeSwitcher';

const meta: Meta<typeof ThemeSwitcher> = {
  component: ThemeSwitcher,
};

export default meta;

type Story = StoryObj<typeof ThemeSwitcher>;

export const Default: Story = {};
