import type { Meta, StoryObj } from '@storybook/nextjs';
import TopSection from '@/components/top-section';

const meta: Meta<typeof TopSection> = {
  component: TopSection,
};

export default meta;

type Story = StoryObj<typeof TopSection>;

export const Default: Story = {};