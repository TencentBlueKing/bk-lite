import type { Meta, StoryObj } from '@storybook/nextjs';
import OperateModal from '@/components/operate-modal';

const meta: Meta<typeof OperateModal> = {
  component: OperateModal,
};

export default meta;

type Story = StoryObj<typeof OperateModal>;

export const Default: Story = {
  args: {
    title: 'Default Title',
    subTitle: 'This is a subtitle',
    footer: null,
    centered: true,
    visible: true,
  },
};

export const WithFooter: Story = {
  args: {
    title: 'Modal with Footer',
    subTitle: 'This is a subtitle',
    footer: <div>Footer Content</div>,
    centered: true,
    visible: true,
  },
};