import type { Meta, StoryObj } from '@storybook/nextjs';
import { Button } from 'antd';
import { expect } from 'storybook/test';
import GridEntityCard from '@/components/grid-entity-card';
import ListPageHeader from '@/components/list-page-header';
import CardGridSkeleton from '@/components/card-grid-skeleton';

const meta = {
  title: 'Data Display/Grid Entity Card',
  component: GridEntityCard,
} satisfies Meta<typeof GridEntityCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LookB: Story = {
  args: {
    name: '生产知识库',
    description: '用于值班问答与变更说明检索。',
    statusTone: 'ok',
    statusLabel: '已上线',
    updatedAt: '3小时前',
    metaLabels: ['RAG', 'Q&A'],
    footer: 'entity',
    owner: 'ops',
    team: ['默认组织', '安全组'],
  },
};

export const ErrorStatus: Story = {
  args: {
    name: '企业微信生产',
    description: '启动失败时应使用失败色，而不是警告色。',
    statusTone: 'error',
    statusLabel: '启动失败',
    updatedAt: '1小时前',
    metaLabels: ['用户同步'],
  },
};

export const CompactCatalog: Story = {
  args: {
    name: '电子邮件',
    description: '通过 SMTP 发送邮件通知。',
  },
};

export const CustomActionFooter: StoryObj = {
  render: () => (
    <div className="grid max-w-[1120px] grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {['系统日志', '文件采集', 'SNMP Trap', 'Kafka 日志订阅'].map((name) => (
        <GridEntityCard
          key={name}
          name={name}
          description="用于集中式日志记录、监控与分析。"
          metaLabels={['通用']}
          footerClassName="w-full"
          footer={<Button type="primary" className="w-full">接入</Button>}
        />
      ))}
    </div>
  ),
  play: async ({ canvasElement }) => {
    const cards = Array.from(canvasElement.querySelectorAll('article'));
    expect(cards).toHaveLength(4);

    cards.forEach((card) => {
      const button = card.querySelector('button');
      expect(button).not.toBeNull();
      const cardRect = card.getBoundingClientRect();
      const buttonRect = button!.getBoundingClientRect();
      expect(buttonRect.top).toBeGreaterThanOrEqual(cardRect.top);
      expect(buttonRect.bottom).toBeLessThanOrEqual(cardRect.bottom);
    });
  },
};

export const HeaderAndSkeleton: StoryObj = {
  render: () => (
    <div className="space-y-4">
      <ListPageHeader
        title="应用"
        description="管理系统应用入口。"
        actions={<Button type="primary">新建</Button>}
      />
      <CardGridSkeleton count={4} />
    </div>
  ),
};
