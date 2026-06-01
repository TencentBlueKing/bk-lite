import type { Meta, StoryObj } from '@storybook/react';
import OneLineEllipsisIntro from '@/app/opspilot/components/oneline-ellipsis-intro';

const meta: Meta<typeof OneLineEllipsisIntro> = {
  component: OneLineEllipsisIntro,
  title: 'OpsPilot/OneLineEllipsisIntro',
};

export default meta;

type Story = StoryObj<typeof OneLineEllipsisIntro>;

export const Default: Story = {
  args: {
    name: 'Knowledge Base Alpha',
    desc: 'This is a knowledge base for internal documentation and FAQ management.',
  },
};

export const LongText: Story = {
  args: {
    name: 'A very long knowledge base name that should be truncated with an ellipsis tooltip when it overflows the container',
    desc: 'This description is also extremely long and should demonstrate how the component handles overflow text with a single line ellipsis and tooltip on hover for better readability.',
  },
};

export const NullValues: Story = {
  args: {
    name: null,
    desc: null,
  },
};
