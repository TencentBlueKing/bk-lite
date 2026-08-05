import React from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import Collapse from '@/components/collapse';
import CustomCascader from '@/components/custom-cascader';

const meta: Meta<typeof Collapse> = {
  component: Collapse,
  title: 'Components/Collapse',
};

export default meta;

type Story = StoryObj<typeof Collapse>;

const organizationList = [
  {
    value: 'zhejiang',
    label: 'Zhejiang',
    children: [
      {
        value: 'hangzhou',
        label: 'Hangzhou',
        children: [
          {
            value: 'xihu',
            label: 'West Lake',
          },
        ],
      },
    ],
  },
  {
    value: 'jiangsu',
    label: 'Jiangsu',
    children: [
      {
        value: 'nanjing',
        label: 'Nanjing',
        children: [
          {
            value: 'zhonghuamen',
            label: 'Zhong Hua Men',
          },
        ],
      },
    ],
  },
];

export const Default: Story = {
  args: {
    title: 'Default Accordion',
    children: <p>This is the content inside the Default Accordion.</p>, // Placeholder content
  },
};

export const WithContent: Story = {
  args: {
    title: 'Accordion with CustomCascader',
    children: (
      <CustomCascader
        className="mr-[8px] w-[250px]"
        showSearch
        maxTagCount="responsive"
        options={organizationList}
        onChange={(value) => console.log('Selected Organizations:', value)}
        multiple
        allowClear
      />
    ),
  },
};

export const SortableAccordion: Story = {
  args: {
    title: 'Sortable Accordion',
    sortable: true,
    children: <p>This accordion can be sorted by dragging.</p>,
    onDragStart: () => console.log('Drag Start'),
    onDragOver: (e) => e.preventDefault(), // Necessary to allow drop
    onDrop: () => console.log('Dropped'),
  },
};
