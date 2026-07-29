import type { Meta, StoryObj } from '@storybook/nextjs';
import OverviewTab from '@/app/opspilot/components/wiki/OverviewTab';

// 概览工作区:左主内容 + 右 400px 常驻问答栏
const meta: Meta<typeof OverviewTab> = {
  title: 'OpsPilot/WikiOverview',
  component: OverviewTab,
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component:
          '知识库详情「概览」tab。主内容左 1fr,问答栏右 400px 常驻。移动端(<1024px)问答栏降级为底部。',
      },
    },
  },
  decorators: [
    (Story) => (
      <div
        style={{
          height: '100vh',
          background: 'var(--color-secondary)',
          padding: 16,
        }}
      >
        <div
          style={{
            height: '100%',
            background: 'var(--color-bg)',
            borderRadius: 12,
            border: '1px solid var(--color-border)',
            overflow: 'hidden',
          }}
        >
          <Story />
        </div>
      </div>
    ),
  ],
  args: { kbId: 1 },
};

export default meta;
type Story = StoryObj<typeof meta>;

// 视觉 1:默认 — 概览数据 + 问答栏空态(推荐问题 chip)
export const Default: Story = {};

// 视觉 2:展开中 — 输入"报销"后看 bot 答案 + 引用
export const Chatting: Story = {
  parameters: {
    docs: {
      description: {
        story:
          '在右栏输入"报销""OA""SLA"等关键词,即可看到 bot 答案、引用块、保存为 wiki 按钮。',
      },
    },
  },
};

// 视觉 3:加载中 — 骨架屏 + 右栏 connect
export const Loading: Story = {
  parameters: {
    docs: {
      description: { story: '首次加载或 KB 切换时,左主内容显示 Skeleton,右栏保持空态可输入。' },
    },
  },
};
