import type { Meta, StoryObj } from '@storybook/nextjs';
import WikiQaAssistant from '@/app/opspilot/components/wiki/WikiQaAssistant';

// 单独看 WikiQaAssistant 组件:对比 floating 与 embedded 两种模式
const meta: Meta<typeof WikiQaAssistant> = {
  title: 'OpsPilot/WikiQaAssistant',
  component: WikiQaAssistant,
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component:
          '知识库问答助手。floating = 右下浮按钮 + 弹窗(旧行为);embedded = 填满父容器、常驻、可收起(新行为)。',
      },
    },
  },
  decorators: [
    (Story) => (
      <div
        style={{
          height: '100vh',
          background: 'var(--color-secondary)',
          padding: 24,
        }}
      >
        <Story />
      </div>
    ),
  ],
  args: { kbId: 1 },
};

export default meta;
type Story = StoryObj<typeof meta>;

// floating 模式:右下角浮按钮 + 弹窗(需要点按钮才出来)
export const Floating: Story = {
  args: { mode: 'floating' },
  decorators: [
    (Story) => (
      <div
        style={{
          height: '100vh',
          position: 'relative',
          background: 'var(--color-secondary)',
          padding: 24,
          color: 'var(--color-text-3)',
        }}
      >
        ← 点击右下角蓝色圆形按钮展开对话弹窗
        <Story />
      </div>
    ),
  ],
};

// embedded 模式:空态(推荐问题)
export const EmbeddedEmpty: Story = {
  args: { mode: 'embedded' },
  decorators: [
    (Story) => (
      <div
        style={{
          height: '100vh',
          padding: 24,
          background: 'var(--color-secondary)',
          display: 'flex',
          justifyContent: 'flex-end',
        }}
      >
        <div style={{ width: 400, height: '100%' }}>
          <Story />
        </div>
      </div>
    ),
  ],
};

// embedded 模式:有对话(需在浏览器手动输入触发,或后接 play 自动)
export const EmbeddedChatting: Story = {
  args: { mode: 'embedded' },
  decorators: [
    (Story) => (
      <div
        style={{
          height: '100vh',
          padding: 24,
          background: 'var(--color-secondary)',
          display: 'flex',
          justifyContent: 'flex-end',
        }}
      >
        <div style={{ width: 400, height: '100%' }}>
          <Story />
        </div>
      </div>
    ),
  ],
  parameters: {
    docs: {
      description: {
        story: '在输入框输入"报销""OA""SLA"等关键词,即可看到完整 bot 答案 + 引用。',
      },
    },
  },
};

// embedded 模式:错误(qa 接口返回 500)
export const EmbeddedError: Story = {
  args: { mode: 'embedded' },
  decorators: [
    (Story) => (
      <div
        style={{
          height: '100vh',
          padding: 24,
          background: 'var(--color-secondary)',
          display: 'flex',
          justifyContent: 'flex-end',
        }}
      >
        <div style={{ width: 400, height: '100%' }}>
          <Story />
        </div>
      </div>
    ),
  ],
  parameters: {
    docs: {
      description: {
        story:
          'qa 接口返回 500 时,bot 消息显示错误占位,输入区仍可继续。可在 mock 里加 trigger 错误,或在浏览器 network throttle 模拟。',
      },
    },
  },
};
