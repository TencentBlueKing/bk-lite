import type { Meta, StoryObj } from '@storybook/nextjs';
import ModelTree from '@/app/opspilot/components/provider/modelTree';
import type { ModelGroup } from '@/app/opspilot/types/provider';

const groups: ModelGroup[] = [
  {
    id: 1,
    name: 'builtin',
    display_name: 'Built-in Models',
    count: 6,
    is_build_in: true,
    index: 1,
  },
  {
    id: 2,
    name: 'production',
    display_name: 'Production Providers',
    count: 4,
    is_build_in: false,
    index: 2,
  },
  {
    id: 3,
    name: 'sandbox',
    display_name: 'Sandbox Evaluation',
    count: 2,
    is_build_in: false,
    index: 3,
  },
];

const meta = {
  title: 'OpsPilot/ModelTree',
  component: ModelTree,
  decorators: [
    (Story) => (
      <div style={{ width: 320, height: 460, padding: 16, background: 'var(--color-fill-1)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof ModelTree>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    filterType: 'llm_model',
    groups,
    selectedGroupId: '2',
    loading: false,
    onGroupSelect: () => {},
    onGroupAdd: () => {},
    onGroupEdit: () => {},
    onGroupDelete: () => {},
    onGroupOrderChange: async () => {},
  },
};

export const Loading: Story = {
  args: {
    ...Default.args,
    loading: true,
  },
};

export const Empty: Story = {
  args: {
    ...Default.args,
    groups: [],
    selectedGroupId: 'all',
  },
};
