import type { Meta, StoryObj } from '@storybook/nextjs';
import GraphExplorer from '@/app/opspilot/components/wiki/GraphExplorer';
import { mockWikiGraph } from '../../.storybook/mocks/opspilot/wiki-api';

const titleOf = (id: number) => mockWikiGraph.nodes.find((n) => n.id === id)?.title || `#${id}`;

// 关系图谱:全幅图 + 浮动工具条/面板(信息以浮层 tip 呈现),不分栏。
// 每个 story 预置不同浮层组合,方便对比版式;面板均可在画布右上工具条实时开关。
const meta: Meta<typeof GraphExplorer> = {
  component: GraphExplorer,
  title: 'OpsPilot/WikiGraph',
  parameters: { layout: 'fullscreen' },
  args: { graph: mockWikiGraph, titleOf, rebuilding: false, height: 'calc(100vh - 32px)' },
  decorators: [
    (Story) => (
      <div style={{ padding: 16, background: 'var(--color-bg-2, #f5f7fa)', height: '100vh' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof GraphExplorer>;

// 版式 1:默认 —— 仅左下社区图例,画面最干净
export const Default: Story = {
  args: { initialPanels: { legend: true } },
};

// 版式 2:开「洞察」—— 右上浮层显示统计 + 最强关联
export const WithInsights: Story = {
  args: { initialPanels: { legend: true, insights: true } },
};

// 版式 3:开「过滤器」—— 左上浮层:节点大小/间距滑块 + 按类型筛选 + 隐藏孤立
export const WithFilters: Story = {
  args: { initialPanels: { legend: true, filter: true } },
};

// 版式 4:全部浮层同时打开(信息最全,接近参考图)
export const AllPanels: Story = {
  args: { initialPanels: { legend: true, filter: true, insights: true } },
};
