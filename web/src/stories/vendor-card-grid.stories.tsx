import type { Meta, StoryObj } from '@storybook/nextjs';
import VendorCardGrid from '@/app/opspilot/components/provider/vendorCardGrid';
import type { ModelVendor } from '@/app/opspilot/types/provider';

const vendors: ModelVendor[] = [
  {
    id: 1,
    name: 'OpenAI Production',
    vendor_type: 'openai',
    protocol_type: 'openai',
    api_base: 'https://api.openai.com/v1',
    description: 'Primary provider for production assistants.',
    enabled: true,
    team: [1],
    team_name: ['Default'],
    model_count: 8,
    permissions: ['View', 'Setting', 'Delete'],
  },
  {
    id: 2,
    name: 'DeepSeek Lab',
    vendor_type: 'deepseek',
    protocol_type: 'openai',
    api_base: 'https://api.deepseek.com/v1',
    description: 'Reasoning models for testing and evaluation.',
    enabled: false,
    team: [2],
    team_name: ['AI Ops'],
    llm_model_count: 2,
    embed_model_count: 1,
    rerank_model_count: 0,
    ocr_model_count: 0,
    permissions: ['View', 'Setting'],
  },
  {
    id: 3,
    name: 'Anthropic Sandbox',
    vendor_type: 'anthropic',
    protocol_type: 'anthropic',
    api_base: 'https://api.anthropic.com',
    description: '',
    enabled: true,
    team: [3],
    team_name: ['Research'],
    model_count: 3,
    permissions: ['View'],
  },
];

const meta = {
  title: 'OpsPilot/VendorCardGrid',
  component: VendorCardGrid,
  decorators: [
    (Story) => (
      <div style={{ minHeight: 320, padding: 16, background: 'var(--color-fill-1)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof VendorCardGrid>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    vendors,
    loading: false,
    onOpen: () => {},
    onEdit: () => {},
    onDelete: () => {},
    onChange: () => {},
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
    vendors: [],
  },
};
