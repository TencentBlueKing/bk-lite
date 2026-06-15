import type { Meta, StoryObj } from '@storybook/nextjs';
import ProviderGrid from '@/app/opspilot/components/provider/grid';
import type { Model } from '@/app/opspilot/types/provider';

const models: Model[] = [
  {
    id: 1,
    name: 'gpt-4o',
    model: 'gpt-4o',
    enabled: true,
    is_build_in: false,
    model_type_name: 'Chat',
    label: 'multimodal',
    icon: 'GPT',
    permissions: ['View', 'Setting', 'Delete'],
  },
  {
    id: 2,
    name: 'deepseek-reasoner',
    model: 'deepseek-reasoner',
    enabled: true,
    is_build_in: false,
    model_type_name: 'Reasoning',
    label: 'reasoning',
    icon: 'DeepSeek',
    permissions: ['View', 'Setting'],
  },
  {
    id: 3,
    name: 'text-embedding-3-large',
    model: 'text-embedding-3-large',
    enabled: false,
    is_build_in: true,
    model_type_name: 'Embedding',
    label: 'text',
    icon: 'GPT',
    permissions: ['View'],
  },
];

const meta = {
  title: 'OpsPilot/ProviderGrid',
  component: ProviderGrid,
  decorators: [
    (Story) => (
      <div style={{ minHeight: 360, padding: 16, background: 'var(--color-fill-1)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof ProviderGrid>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    models,
    filterType: 'llm_model',
    loading: false,
    setModels: () => {},
    onRefreshData: () => {},
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
    models: [],
  },
};
