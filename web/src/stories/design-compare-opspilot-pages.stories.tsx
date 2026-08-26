'use client';

import type { Meta, StoryObj } from '@storybook/nextjs';
import {
  ALL_PAGE_EFFECTS,
  PageMemoryConfig,
  PageMemoryList,
  PageMemoryMemories,
  PageOpsilotRedirect,
  PageProviderDetail,
  PageProviderList,
  PageSettingsManage,
  PageSettingsQuota,
  PageSettingsRedirect,
  PageSkillDetailRedirect,
  PageSkillList,
  PageSkillRules,
  PageSkillSettings,
  PageStudioApi,
  PageStudioChannel,
  PageStudioChat,
  PageStudioDetailRedirect,
  PageStudioList,
  PageStudioLogInfo,
  PageStudioSettings,
  PageStudioStatistics,
  PageToolList,
  PageUnifiedEntityLists,
  PageWikiDetail,
  PageWikiList,
} from './design-compare/opspilot-page-effects';

function AllPagesGallery() {
  return (
    <div style={{ display: 'grid', gap: 24, padding: 16, background: 'var(--color-fill-1)' }}>
      <div
        style={{
          padding: 14,
          borderRadius: 8,
          border: '1px solid var(--color-border)',
          background: 'var(--color-bg)',
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--color-text-1)' }}>
          OpsPilot 全页面 After 效果图（24）
        </div>
        <div style={{ marginTop: 6, fontSize: 13, color: 'var(--color-text-3)', lineHeight: 1.55 }}>
          Token 对齐：`--color-bg` / `--color-border` / `--color-fill-*` / `--color-text-*`，随
          `html.light|dark` 切换。全列表统一选型 Look B 卡（`UnifiedOpsCard`）。Story 示意，非改生产。
        </div>
      </div>
      {ALL_PAGE_EFFECTS.map((p) => (
        <div key={p.id}>{p.render()}</div>
      ))}
    </div>
  );
}

const meta = {
  title: 'Design/OpsPilot Page Effects',
  component: AllPagesGallery,
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component:
          '全部 OpsPilot 路由的 After 效果图：Beautiful UI 交互/布局 × OpsPilot 主题与 Ant Design。',
      },
    },
  },
} satisfies Meta<typeof AllPagesGallery>;

export default meta;

type Story = StoryObj<typeof meta>;

export const All24Pages: Story = {
  name: '00 All pages (+ unified lists intro)',
};

export const S00UnifiedEntityLists: Story = {
  name: '00 Unified entity lists (6 modules)',
  render: () => <PageUnifiedEntityLists />,
};

export const S01OpsilotRedirect: Story = {
  name: '01 Opsilot redirect',
  render: () => <PageOpsilotRedirect />,
};
export const S02StudioList: Story = {
  name: '02 工作台 list',
  render: () => <PageStudioList />,
};
export const S03StudioDetail: Story = {
  name: '03 Studio detail redirect',
  render: () => <PageStudioDetailRedirect />,
};
export const S04StudioSettings: Story = {
  name: '04 Studio settings',
  render: () => <PageStudioSettings />,
};
export const S05StudioChannel: Story = {
  name: '05 Studio channel',
  render: () => <PageStudioChannel />,
};
export const S06StudioApi: Story = {
  name: '06 Studio API',
  render: () => <PageStudioApi />,
};
export const S07StudioStatistics: Story = {
  name: '07 Studio statistics',
  render: () => <PageStudioStatistics />,
};
export const S08StudioLog: Story = {
  name: '08 Studio log',
  render: () => <PageStudioLogInfo />,
};
export const S09StudioChat: Story = {
  name: '09 Studio chat',
  render: () => <PageStudioChat />,
};
export const S10SkillList: Story = {
  name: '10 智能体 list',
  render: () => <PageSkillList />,
};
export const S11SkillDetail: Story = {
  name: '11 Skill detail redirect',
  render: () => <PageSkillDetailRedirect />,
};
export const S12SkillSettings: Story = {
  name: '12 Skill settings',
  render: () => <PageSkillSettings />,
};
export const S13SkillRules: Story = {
  name: '13 Skill rules',
  render: () => <PageSkillRules />,
};
export const S14WikiList: Story = {
  name: '14 知识库 list',
  render: () => <PageWikiList />,
};
export const S15WikiDetail: Story = {
  name: '15 Wiki detail',
  render: () => <PageWikiDetail />,
};
export const S16ToolList: Story = {
  name: '16 工具 list',
  render: () => <PageToolList />,
};
export const S17ProviderList: Story = {
  name: '17 模型 list',
  render: () => <PageProviderList />,
};
export const S18ProviderDetail: Story = {
  name: '18 供应商详情',
  render: () => <PageProviderDetail />,
};
export const S19MemoryList: Story = {
  name: '19 记忆 list',
  render: () => <PageMemoryList />,
};
export const S20MemoryMemories: Story = {
  name: '20 记忆',
  render: () => <PageMemoryMemories />,
};
export const S21MemoryConfig: Story = {
  name: '21 记忆配置',
  render: () => <PageMemoryConfig />,
};
export const S22SettingsRedirect: Story = {
  name: '22 设置入口',
  render: () => <PageSettingsRedirect />,
};
export const S23SettingsQuota: Story = {
  name: '23 我的配额',
  render: () => <PageSettingsQuota />,
};
export const S24SettingsManage: Story = {
  name: '24 管理配额',
  render: () => <PageSettingsManage />,
};
