import type { Meta, StoryObj } from '@storybook/nextjs';
import { Button } from 'antd';
import SystemManagerUnifiedCard from '@/app/system-manager/components/system-manager-unified-card';
import CardGridSkeleton from '@/components/card-grid-skeleton';
import ListPageHeader from '@/components/list-page-header';

const meta = {
  title: 'System Manager/Unified Card',
  component: SystemManagerUnifiedCard,
} satisfies Meta<typeof SystemManagerUnifiedCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const LookB: Story = {
  args: {
    name: '企业微信生产',
    description: '用于员工同步与登录认证的企业微信接入。',
    icon: 'qiwei2',
    statusTone: 'ok',
    statusLabel: '已启动',
    updatedAt: '3小时前',
    meta: ['用户同步', '登录认证', 'IM 通知'],
    footer: 'entity',
    owner: 'ops',
    team: ['默认组织', '安全组'],
    menuItems: [
      { key: 'edit', label: '编辑' },
      { key: 'delete', label: '删除', danger: true },
    ],
  },
};

export const ApplicationOrigin: Story = {
  args: {
    name: 'CMDB',
    description: '用于集中管理企业的所有 IT 资产和资源的平台。',
    icon: 'cmdb',
    origin: 'builtin',
    meta: ['资产数据', '自动发现', '模型自定义'],
    onClick: () => {},
  },
};

export const ExternalApp: Story = {
  args: {
    name: 'ITSM',
    description: '通过标准化处理、问题与变更管理流程，实现IT服务的全生命周期管理。',
    icon: 'itsm',
    origin: 'external',
    onClick: () => {},
  },
};

export const ChannelCard: Story = {
  args: {
    name: '电子邮件',
    description: '通过 SMTP 发送邮件通知。',
    icon: 'youjian',
    onClick: () => {},
  },
};

export const UserSyncPaused: Story = {
  args: {
    name: '本地预览 · 企业微信同步',
    description: '悬停「已暂停」应看到依赖不可用原因。',
    icon: 'qiwei2',
    warningLabel: '已暂停',
    warningTooltip: '集成实例已禁用',
    caption: (
      <>
        <span>企业微信生产</span>
        <span className="mx-1">·</span>
        <span>根组织默认组织</span>
      </>
    ),
    menuItems: [
      { key: 'strategy', label: '同步策略' },
    ],
    body: (
      <div className="flex flex-col gap-2">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <div className="min-w-0 truncate text-xs leading-5 text-[var(--color-text-3)]">
            <span>最近同步 --</span>
            <span className="mx-1">·</span>
            <span>暂无记录</span>
          </div>
          <Button type="primary" size="small" className="shrink-0" disabled>
            立即同步
          </Button>
        </div>
      </div>
    ),
  },
};

export const HeaderAndSkeleton: Story = {
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
