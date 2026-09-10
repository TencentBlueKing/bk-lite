'use client';

import type { Meta, StoryObj } from '@storybook/nextjs';
import AppTopNav from '@/app/(core)/components/top-menu/appTopNav';
import AppTopSideNav from '@/app/(core)/components/app-top-side-nav';
import { ConsoleLayoutProvider } from '@/console-layout';
import type { ClientData, MenuItem } from '@/types/index';

const SIDE_MENUS: MenuItem[] = [
  { title: '工作台', url: '/opspilot/studio', name: 'bot_list', icon: 'jiqiren2', operation: [] },
  { title: '智能体', url: '/opspilot/agents', name: 'agents', icon: 'weibiaoti3', operation: [] },
  { title: '知识库', url: '/opspilot/wiki', name: 'wiki_list', icon: 'zhishiku', operation: [] },
  { title: '工具', url: '/opspilot/tools', name: 'tools', icon: 'gongju-', operation: [] },
  { title: '记忆', url: '/opspilot/memory', name: 'memory', icon: 'shujuguanli', operation: [] },
  { title: '模型', url: '/opspilot/models', name: 'models', icon: 'moxing2', operation: [] },
];
import {
  ConsoleAppTopChromeNow,
  ConsoleAppTopChromeProposed,
} from './design-compare/console-app-top-chrome-effect';

const OVERFLOW_APPS = [
  ['opspilot', 'OpsPilot'],
  ['ops-console', '控制台'],
  ['system-manager', '系统管理'],
  ['cmdb', 'CMDB'],
  ['monitor', '监控中心'],
  ['log', '日志中心'],
  ['node', '节点管理'],
  ['alarm', '告警中心'],
  ['itsm', 'ITSM'],
  ['ops-analysis', '运营分析'],
  ['mlops', 'MLOps'],
  ['lab', 'Lab'],
].map(([name, display_name]) => ({
  id: name,
  name,
  display_name,
  description: display_name,
  url: `/${name}`,
  icon: name,
  is_build_in: true,
})) as ClientData[];

function Gallery() {
  return (
    <div className="grid gap-6 bg-[var(--color-fill-1)] p-4">
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3.5">
        <div className="text-base font-semibold text-[var(--color-text-1)]">
          应用顶栏壳层 + OpsPilot 卡片对照
        </div>
        <div className="mt-1.5 text-[13px] leading-relaxed text-[var(--color-text-3)]">
          Story 示意，非改生产。建议版：壳层选中态 + Look B 统一卡；现状版：渐变头卡对照。
        </div>
      </div>
      <ConsoleAppTopChromeProposed />
      <ConsoleAppTopChromeNow />
    </div>
  );
}

const meta = {
  title: 'Design/Console App-Top Chrome',
  component: Gallery,
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component:
          '应用顶栏布局与 OpsPilot 卡片对照。Proposed = 壳层层次 + Look B 统一卡；Now = 现状渐变头卡。',
      },
    },
  },
} satisfies Meta<typeof Gallery>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Proposed: Story = {
  name: '01 Proposed（壳层 + B 卡）',
  render: () => <ConsoleAppTopChromeProposed />,
};

export const Now: Story = {
  name: '02 Now（现状渐变卡）',
  render: () => <ConsoleAppTopChromeNow />,
};

export const Compare: Story = {
  name: '00 Compare（上下对照）',
};

export const SideRailCollapse: Story = {
  name: '04 左栏收起 / 悬停浮出',
  render: () => (
    <ConsoleLayoutProvider>
      <div className="bg-[var(--color-fill-1)] p-8">
        <div className="mb-3 text-sm text-[var(--color-text-3)]">
          底部按钮收起为纯图标栏；收起后移入浮出完整导航但不挤内容，点展开才占位。
        </div>
        <div className="flex h-[420px] overflow-hidden rounded-lg border border-[var(--color-border-1)]">
          <AppTopSideNav menus={SIDE_MENUS} pathname="/opspilot/studio" />
          <div className="min-w-0 flex-1 p-4">
            <div className="h-full rounded-lg bg-[var(--color-bg-1)] p-4 text-sm text-[var(--color-text-3)]">
              内容区。收起时这块宽度不会随着悬停变化。
            </div>
          </div>
        </div>
      </div>
    </ConsoleLayoutProvider>
  ),
};

export const AppStripOverflow: Story = {
  name: '03 应用条溢出箭头',
  render: () => (
    <div className="bg-[var(--color-fill-1)] p-8">
      <div className="mb-3 text-sm text-[var(--color-text-3)]">
        窄栏下溢出用小箭头滚动，不要「更多 / 详情」文字。
      </div>
      <div className="w-[560px] rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-3">
        <AppTopNav apps={OVERFLOW_APPS} pathname="/opspilot" />
      </div>
    </div>
  ),
};
