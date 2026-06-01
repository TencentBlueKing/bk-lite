import type { Meta, StoryObj } from '@storybook/react';
import RedirectToFirstMenu from '@/components/redirect-menu';

const meta: Meta<typeof RedirectToFirstMenu> = {
  component: RedirectToFirstMenu,
  title: 'Components/RedirectToFirstMenu',
  parameters: {
    docs: {
      description: {
        component: 'Redirects to the first available menu URL on mount. Renders nothing visually.',
      },
    },
  },
};

export default meta;

type Story = StoryObj<typeof RedirectToFirstMenu>;

export const Default: Story = {};
