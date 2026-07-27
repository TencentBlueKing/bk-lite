import type { Meta, StoryObj } from '@storybook/react';
import React from 'react';
import { Button, Card, Form, Space } from 'antd';
import DynamicForm from '@/components/dynamic-form';
import GroupTreeSelect from '@/components/group-tree-select';
import SectionHeader from '@/components/section-header';

const baseFields = [
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

const governedFields = [
  {
    name: 'name',
    type: 'input',
    label: 'Knowledge base name',
    placeholder: 'Enter a workspace name',
    rules: [{ required: true, message: 'Name is required' }],
  },
  {
    name: 'manageGroups',
    type: 'groupTreeSelect',
    label: 'Manage groups',
    placeholder: 'Select manage groups',
    multiple: true,
    showSearch: true,
    allowClear: true,
    lockedValues: [11],
  },
  {
    name: 'ownerGroup',
    type: 'groupTreeSelect',
    label: 'Owner group',
    placeholder: 'Select owner group',
    multiple: false,
    filterByRootId: 1,
  },
];

const DataEntryFamilyOverview = () => {
  const [basicForm] = Form.useForm();
  const [governedForm] = Form.useForm();
  const [bindingForm] = Form.useForm();

  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Dynamic form contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader
              className="mb-3"
              title="Baseline field composition"
              titleClassName="text-sm font-medium"
              description="Shared field mapping keeps plain inputs, textarea, and select controls on a single governed form surface."
            />
            <DynamicForm form={basicForm} fields={baseFields} />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader
              className="mb-3"
              title="Embedded group ownership fields"
              titleClassName="text-sm font-medium"
              description="DynamicForm directly composes GroupTreeSelect so shared forms can mix text entry and ownership assignment without app-local field renderers."
            />
            <DynamicForm
              form={governedForm}
              fields={governedFields}
              initialValues={{ manageGroups: [11, 12], ownerGroup: 12 }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Group tree select contract" titleClassName="text-sm font-semibold" />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Multiple and single modes" titleClassName="text-sm font-medium" />
            <div className="space-y-4">
              <Form layout="vertical">
                <Form.Item label="Multiple groups">
                  <GroupTreeSelect placeholder="Select groups" multiple />
                </Form.Item>
                <Form.Item label="Single group">
                  <GroupTreeSelect placeholder="Select single group" multiple={false} />
                </Form.Item>
              </Form>
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Search, clear, and locked values" titleClassName="text-sm font-medium" />
            <div className="space-y-4">
              <GroupTreeSelect
                placeholder="Search groups"
                multiple
                showSearch
                allowClear
                value={[11, 12]}
              />
              <GroupTreeSelect
                placeholder="Manage groups"
                multiple
                allowClear
                value={[11, 12]}
                lockedValues={[11]}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Form binding and subtree filter" titleClassName="text-sm font-medium" />
            <Card size="small" bodyStyle={{ padding: 12 }}>
              <Form form={bindingForm} layout="vertical">
                <Form.Item name="multipleGroups" label="Multiple groups">
                  <GroupTreeSelect placeholder="Select multiple groups" multiple />
                </Form.Item>
                <Form.Item name="singleGroup" label="Filtered subtree">
                  <GroupTreeSelect placeholder="Frontend subtree only" multiple={false} filterByRootId={1} />
                </Form.Item>
                <Form.Item className="mb-0">
                  <Space wrap>
                    <Button
                      type="primary"
                      onClick={() => {
                        bindingForm.setFieldsValue({
                          multipleGroups: [11, 12],
                          singleGroup: 12,
                        });
                      }}
                    >
                      Set test values
                    </Button>
                    <Button onClick={() => bindingForm.resetFields()}>Reset</Button>
                  </Space>
                </Form.Item>
              </Form>
            </Card>
          </div>
        </div>
      </section>

      <section className="space-y-2 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Storybook structure" titleClassName="text-sm font-semibold" />
        <div className="text-sm text-[var(--color-text-2)]">
          The DataEntry family is governed through shared field-composition and group-ownership selection contracts instead of separate leaf stories for each form primitive.
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Framework/DataEntry/FamilyOverview',
  component: DataEntryFamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1180, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof DataEntryFamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
