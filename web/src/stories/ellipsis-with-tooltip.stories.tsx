import type { Meta, StoryObj } from '@storybook/nextjs';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

const meta: Meta<typeof EllipsisWithTooltip> = {
  title: 'Components/EllipsisWithTooltip',
  component: EllipsisWithTooltip,
  args: {
    className: 'w-full overflow-hidden text-ellipsis whitespace-nowrap text-sm',
  },
  decorators: [
    (Story) => (
      <div className="w-[240px] rounded border border-[var(--color-border-1)] p-3">
        <Story />
      </div>
    ),
  ],
  parameters: {
    nextjs: {
      appDirectory: true,
      navigation: { pathname: '/ops-analysis/render/execution/1' },
    },
  },
};

export default meta;

type Story = StoryObj<typeof EllipsisWithTooltip>;

// 长文本示例
export const LongText: Story = {
  args: {
    text: '这是一段非常非常长的文本内容，它可能会超出容器的宽度显示，当超出时应该显示省略号并在悬停时展示完整内容。',
  },
};

export const InteractiveOverflow: Story = {
  args: {
    text: '/var/lib/kubelet/pods/checkout-production-7f8b9c6d5-very-long-volume-name/data',
    disclosure: 'interactive',
  },
};

// 短文本示例
export const ShortText: Story = {
  args: {
    text: '短文本',
  },
};

// 自定义样式示例
export const CustomStyle: Story = {
  args: {
    text: '自定义样式的文本',
    className: 'text-lg font-bold mb-2 whitespace-nowrap overflow-hidden text-ellipsis',
  },
};
