import type { Meta, StoryObj } from '@storybook/react';
import React from 'react';
import { Form, Button, Space, Card } from 'antd';
import GroupTreeSelect from '@/components/group-tree-select';

const meta: Meta<typeof GroupTreeSelect> = {
  title: 'Components/GroupTreeSelect',
  component: GroupTreeSelect,
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component: 'Tree-based group selector component built on Ant Design TreeSelect, supporting multiple/single selection modes with automatic user group data fetching and perfect form binding.'
      }
    }
  },
  tags: ['autodocs'],
  argTypes: {
    multiple: {
      control: 'boolean',
      description: 'Enable multiple selection mode'
    },
    disabled: {
      control: 'boolean',
      description: 'Disable the component'
    },
    placeholder: {
      control: 'text',
      description: 'Placeholder text'
    }
  }
};

export default meta;
type Story = StoryObj<typeof meta>;

// Basic usage
export const Default: Story = {
  args: {
    placeholder: 'Select groups',
    multiple: true,
  },
  render: (args) => {
    const [form] = Form.useForm();

    return (
      <div style={{ width: 400 }}>
        <Form form={form} layout="vertical">
          <Form.Item
            name="groups"
            label="Select Groups"
            rules={[{ required: true, message: 'Please select groups' }]}
          >
            <GroupTreeSelect {...args} />
          </Form.Item>
        </Form>
      </div>
    );
  }
};

// Single selection mode
export const SingleSelect: Story = {
  args: {
    placeholder: 'Select single group',
    multiple: false,
  },
  render: (args) => {
    const [form] = Form.useForm();

    return (
      <div style={{ width: 400 }}>
        <Form form={form} layout="vertical">
          <Form.Item
            name="group"
            label="Select Single Group"
          >
            <GroupTreeSelect {...args} />
          </Form.Item>
        </Form>
      </div>
    );
  }
};

// Two-way binding demonstration
export const TwoWayBinding: Story = {
  render: () => {
    const [form] = Form.useForm();

    const handleSubmit = (values: any) => {
      alert(`Submitted values: ${JSON.stringify(values, null, 2)}`);
    };

    const setTestValues = () => {
      form.setFieldsValue({
        multipleGroups: ['group1', 'group2'],
        singleGroup: 'group3'
      });
    };

    const getCurrentValues = () => {
      const values = form.getFieldsValue();
      alert(`Current values: ${JSON.stringify(values, null, 2)}`);
    };

    return (
      <div style={{ width: 600 }}>
        <Card title="Two-way Binding Demo">
          <Form form={form} layout="vertical" onFinish={handleSubmit}>
            <Form.Item
              name="multipleGroups"
              label="Multiple Groups"
              rules={[{ required: true, message: 'Please select groups' }]}
            >
              <GroupTreeSelect
                placeholder="Select multiple groups"
                multiple={true}
              />
            </Form.Item>

            <Form.Item
              name="singleGroup"
              label="Single Group"
            >
              <GroupTreeSelect
                placeholder="Select single group"
                multiple={false}
              />
            </Form.Item>

            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit">
                  Submit & View Values
                </Button>
                <Button onClick={getCurrentValues}>
                  Get Current Values
                </Button>
                <Button onClick={setTestValues}>
                  Set Test Values
                </Button>
                <Button onClick={() => form.resetFields()}>
                  Reset
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Card>
      </div>
    );
  }
};

// Disabled state
export const Disabled: Story = {
  args: {
    placeholder: 'Disabled state',
    disabled: true,
  },
  render: (args) => {
    const [form] = Form.useForm();

    React.useEffect(() => {
      form.setFieldsValue({
        groups: ['group1', 'group2']
      });
    }, [form]);

    return (
      <div style={{ width: 400 }}>
        <Form form={form} layout="vertical">
          <Form.Item
            name="groups"
            label="Disabled State"
          >
            <GroupTreeSelect {...args} />
          </Form.Item>
        </Form>
      </div>
    );
  }
};

// Custom styling
export const CustomStyle: Story = {
  args: {
    placeholder: 'Custom styling',
    style: { width: '100%', borderRadius: '8px' },
  },
  render: (args) => {
    const [form] = Form.useForm();

    return (
      <div style={{ width: 500 }}>
        <Form form={form} layout="vertical">
          <Form.Item
            name="groups"
            label="Custom Styling"
          >
            <GroupTreeSelect {...args} />
          </Form.Item>
        </Form>
      </div>
    );
  }
};
