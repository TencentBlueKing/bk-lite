import type { Meta, StoryObj } from '@storybook/nextjs';

import ContentDrawer from '@/components/content-drawer';

const meta: Meta<typeof ContentDrawer> = {
  component: ContentDrawer,
};

export default meta;

type Story = StoryObj<typeof ContentDrawer>;

export const Default: Story = {
  args: {
    visible: false,
    content: 'This is a content drawer',
  },
};
