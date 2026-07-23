import type { Meta, StoryObj } from '@storybook/nextjs';
import { Card, message } from 'antd';
import { DeleteOutlined, EditOutlined } from '@ant-design/icons';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import { useTranslation } from '@/utils/i18n';

const meta: Meta<typeof MoreActionsDropdown> = {
  component: MoreActionsDropdown,
  title: 'Interaction/MoreActionsDropdown',
  decorators: [
    (Story) => (
      <div style={{ padding: 32, background: '#fff', display: 'inline-block' }}>
        <Story />
      </div>
    ),
  ],
};

export default meta;

type Story = StoryObj<typeof MoreActionsDropdown>;

const baseItems: MoreActionsDropdownItem[] = [
  {
    key: 'edit',
    label: '编辑',
    onClick: () => message.info('编辑'),
  },
  {
    key: 'duplicate',
    label: '复制',
    onClick: () => message.info('复制'),
  },
  {
    key: 'archive',
    label: '归档',
    onClick: () => message.info('归档'),
  },
  {
    key: 'delete',
    label: '删除',
    danger: true,
    confirm: { title: '确认删除？', content: '该操作不可撤销。' },
    onClick: () => message.success('已删除'),
  },
];

export const Default: Story = {
  args: {
    items: baseItems,
  },
};

export const Empty: Story = {
  args: { items: [] },
};

export const AllDisabled: Story = {
  args: {
    items: [
      { key: 'edit', label: '编辑', disabled: true },
      { key: 'duplicate', label: '复制', disabled: true },
    ],
  },
};

export const LongLabels: Story = {
  args: {
    items: [
      {
        key: 'export-with-permission',
        label: '导出当前选中并附带原始权限快照',
        onClick: () => message.info('export'),
      },
      {
        key: 'rotate-and-revalidate',
        label: '轮换凭据并触发全量重新校验流程',
        danger: true,
        confirm: { title: '确认执行？', content: '会触发所有依赖资源重新拉取。' },
        onClick: () => message.success('rotate'),
      },
    ],
  },
};

export const InsideCard: Story = {
  render: (args) => (
    <Card
      title="资源示例"
      extra={<MoreActionsDropdown {...args} />}
      style={{ width: 360 }}
    >
      <p className="text-sm text-[var(--color-text-2)]">
        卡片右上角触发的更多操作,模拟行/卡片场景。
      </p>
    </Card>
  ),
  args: { items: baseItems, stopPropagation: true },
};

export const LinkButtonVariant: Story = {
  args: {
    items: baseItems,
    buttonType: 'link',
  },
};

export const WithIcons: Story = {
  render: (args) => {
    const { t } = useTranslation();
    return (
      <MoreActionsDropdown
        {...args}
        items={[
          { key: 'edit', label: t('common.edit'), icon: <EditOutlined />, onClick: () => message.info('edit') },
          { key: 'delete', label: t('common.delete'), icon: <DeleteOutlined />, danger: true, onClick: () => message.info('delete') },
        ]}
      />
    );
  },
};