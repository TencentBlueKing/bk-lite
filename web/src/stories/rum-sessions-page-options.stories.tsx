'use client';

import type { Meta, StoryObj } from '@storybook/nextjs';
import {
  RUM_SESSIONS_OPTIONS,
  RumSessionsOptionACurrent,
  RumSessionsOptionBSingleWorkbench,
  RumSessionsOptionCDualWorkbench,
  RumSessionsOptionDCardGrid,
} from './design-compare/rum-sessions-page-effects';

function Gallery() {
  return (
    <div className="grid gap-6 bg-[var(--color-fill-1)] p-4">
      <div className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] p-4">
        <div className="text-base font-semibold text-[var(--color-text-1)]">
          RUM 会话页布局选型（4 套）
        </div>
        <p className="mb-0 mt-1.5 text-[13px] leading-relaxed text-[var(--color-text-3)]">
          对齐 OpsPilot Look B 卡与 Studio Workbench，不另发明皮肤。请在 Storybook 里逐个对比后告诉我选
          A/B/C/D（或组合，例如「B 的摘要条 + C 的左栏」）。选定后再改生产页。
        </p>
        <ul className="mb-0 mt-3 list-disc space-y-1 pl-5 text-[13px] text-[var(--color-text-2)]">
          {RUM_SESSIONS_OPTIONS.map((opt) => (
            <li key={opt.id}>
              <span className="font-medium text-[var(--color-text-1)]">{opt.name}</span>
              {' — '}
              {opt.summary}
            </li>
          ))}
        </ul>
      </div>
      {RUM_SESSIONS_OPTIONS.map((opt) => (
        <div key={opt.id} className="overflow-hidden rounded-lg border border-[var(--color-border-1)]">
          {opt.render()}
        </div>
      ))}
    </div>
  );
}

const meta = {
  title: 'Design/RUM Sessions Page Options',
  component: Gallery,
  parameters: {
    layout: 'fullscreen',
    docs: {
      description: {
        component:
          'RUM `/rum/sessions` 布局选型示意。B/C/D 对齐 OpsPilot 工作台与 Look B；A 为当前对照。Story only。',
      },
    },
  },
} satisfies Meta<typeof Gallery>;

export default meta;

type Story = StoryObj<typeof meta>;

export const AllOptions: Story = {
  name: '00 全部对比',
};

export const OptionACurrent: Story = {
  name: 'A · 当前态（对照）',
  render: () => <RumSessionsOptionACurrent />,
};

export const OptionBSingleWorkbench: Story = {
  name: 'B · 单面板工作台',
  render: () => <RumSessionsOptionBSingleWorkbench />,
};

export const OptionCDualWorkbench: Story = {
  name: 'C · 双栏工作台',
  render: () => <RumSessionsOptionCDualWorkbench />,
};

export const OptionDCardGrid: Story = {
  name: 'D · Look B 会话卡',
  render: () => <RumSessionsOptionDCardGrid />,
};
