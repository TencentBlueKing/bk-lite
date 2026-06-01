import type { Meta, StoryObj } from '@storybook/react';
import SearchCombination from '@/components/search-combination';
import type { FieldConfig } from '@/components/search-combination/types';

const meta: Meta<typeof SearchCombination> = {
  component: SearchCombination,
  title: 'Components/SearchCombination',
};

export default meta;

type Story = StoryObj<typeof SearchCombination>;

const fieldConfigs: FieldConfig[] = [
  {
    name: 'operating_system',
    label: 'OS',
    lookup_expr: 'in',
    options: [
      { id: 'linux', name: 'Linux' },
      { id: 'windows', name: 'Windows' },
      { id: 'macos', name: 'macOS' },
    ],
  },
  {
    name: 'ip',
    label: 'IP Address',
    lookup_expr: 'icontains',
  },
  {
    name: 'is_active',
    label: 'Active',
    lookup_expr: 'bool',
  },
];

export const Default: Story = {
  args: {
    fieldConfigs,
  },
};

export const CustomWidth: Story = {
  args: {
    fieldConfigs,
    fieldWidth: 200,
    selectWidth: 120,
  },
};
