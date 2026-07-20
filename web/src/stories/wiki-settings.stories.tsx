import type { Meta, StoryObj } from '@storybook/nextjs';
import SettingsTab from '@/app/opspilot/components/wiki/SettingsTab';

const meta: Meta<typeof SettingsTab> = {
  component: SettingsTab,
  title: 'OpsPilot/WikiSettings',
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <div style={{ padding: 24, background: '#fff', minHeight: 520 }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof SettingsTab>;

// 设置工作区(左侧导航 + 右内容),数据由 .storybook/mocks/opspilot/wiki-api 提供
export const Default: Story = {
  args: { kbId: 1 },
};
