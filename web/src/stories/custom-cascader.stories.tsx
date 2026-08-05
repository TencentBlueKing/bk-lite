import type { Meta, StoryObj } from '@storybook/nextjs';
import CustomCascader from '@/components/custom-cascader';

const meta: Meta<typeof CustomCascader> = {
  component: CustomCascader,
  title: 'Components/CustomCascader',
  argTypes: {
    onChange: { action: 'changed' },  // 监测 onChange 事件
  },
};

export default meta;

type Story = StoryObj<typeof CustomCascader>;

const defaultOptions = [
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

export const SingleSelect: Story = {
  args: {
    placeholder: 'Please select',
    options: defaultOptions,
    value: [],
    multiple: false,
  },
};

export const MultipleSelect: Story = {
  args: {
    placeholder: 'Please select more than one',
    options: defaultOptions,
    value: [],
    multiple: true,
  },
};

export const PreSelectValue: Story = {
  args: {
    placeholder: 'Please select',
    options: defaultOptions,
    value: ['zhejiang', 'hangzhou', 'xihu'],
    multiple: true,
  },
};
