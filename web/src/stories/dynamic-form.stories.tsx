import React from 'react';
import { Meta, StoryObj } from '@storybook/nextjs';
import { Form } from 'antd';
import DynamicForm from '@/components/dynamic-form';

const meta: Meta<typeof DynamicForm> = {
  component: DynamicForm,
  title: 'Components/DynamicForm',
};

export default meta;

type Story = StoryObj<typeof DynamicForm>;

const fields = [
  {
    name: 'username',
    type: 'input',
    label: 'Username',
    placeholder: 'Enter your username',
    rules: [{ required: true, message: 'Username is required' }],
  },
  {
    name: 'bio',
    type: 'textarea',
    label: 'Bio',
    placeholder: 'Tell us about yourself',
  },
  {
    name: 'gender',
    type: 'select',
    label: 'Gender',
    placeholder: 'Select gender',
    options: [
      { value: 'male', label: 'Male' },
      { value: 'female', label: 'Female' },
    ],
    rules: [{ required: true, message: 'Gender is required' }],
  },
];

export const Default: Story = {
  render: () => {
    const [form] = Form.useForm();
    return <DynamicForm form={form} fields={fields} />;
  },
};
