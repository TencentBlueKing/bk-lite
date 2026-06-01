import type { Meta, StoryObj } from '@storybook/react';
import MultiCascadePanel from '@/components/multi-cascade-panel';
import type { CascadeNode } from '@/components/multi-cascade-panel';

const meta: Meta<typeof MultiCascadePanel> = {
  component: MultiCascadePanel,
  title: 'Components/MultiCascadePanel',
};

export default meta;

type Story = StoryObj<typeof MultiCascadePanel>;

const mockData: CascadeNode[] = [
  {
    value: 1,
    label: 'Asia',
    children: [
      {
        value: 11,
        label: 'China',
        children: [
          { value: 111, label: 'Beijing' },
          { value: 112, label: 'Shanghai' },
          { value: 113, label: 'Guangzhou' },
        ],
      },
      {
        value: 12,
        label: 'Japan',
        children: [
          { value: 121, label: 'Tokyo' },
          { value: 122, label: 'Osaka' },
        ],
      },
    ],
  },
  {
    value: 2,
    label: 'Europe',
    children: [
      {
        value: 21,
        label: 'United Kingdom',
        children: [
          { value: 211, label: 'London' },
          { value: 212, label: 'Manchester' },
        ],
      },
      {
        value: 22,
        label: 'France',
        children: [
          { value: 221, label: 'Paris' },
        ],
      },
    ],
  },
];

export const Default: Story = {
  args: {
    data: mockData,
    searchable: true,
    searchPlaceholder: 'Search...',
  },
};

export const SingleSelect: Story = {
  args: {
    data: mockData,
    single: true,
  },
};

export const CascadeMode: Story = {
  args: {
    data: mockData,
    cascade: true,
  },
};

export const WithPreselected: Story = {
  args: {
    data: mockData,
    value: [111, 112, 211],
  },
};
