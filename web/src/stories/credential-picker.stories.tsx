import type { Meta, StoryObj } from '@storybook/nextjs';
import React, { useState } from 'react';
import { Button, Form } from 'antd';
import { IntlProvider } from 'react-intl';
import {
  CredentialPickerChrome,
  CredentialQuickCreateForm,
} from '@/components/credential-picker';
import type { CredentialTypeItem } from '@/components/credential-picker';
import zhCommon from '@/locales/zh.json';
import zhSystem from '@/app/system-manager/locales/zh.json';

type LocaleJson = Record<string, unknown>;

function flatten(obj: LocaleJson, prefix = '', out: Record<string, string> = {}) {
  Object.keys(obj).forEach((key) => {
    const value = obj[key];
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      flatten(value as LocaleJson, path, out);
    } else {
      out[path] = String(value);
    }
  });
  return out;
}

const pickerMessages = {
  ...flatten(zhCommon as LocaleJson),
  ...flatten(zhSystem as LocaleJson),
};

const OPTIONS = [
  { label: '生产跳板机 SSH - SSH (crd-ssh-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)', value: 'crd-ssh-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' },
  { label: '生产 MySQL 只读 - SQL (crd-sql-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb)', value: 'crd-sql-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' },
];

const SSH_TYPE: CredentialTypeItem = {
  key: 'ssh',
  name: 'SSH',
  is_builtin: true,
  categories: ['host'],
  fields: [
    { id: 'auth_method', name: '认证方式', kind: 'enum', values: ['password', 'key'], required: true, default: 'password' },
    { id: 'username', name: '用户名', kind: 'string', required: true },
    { id: 'password', name: '密码', kind: 'secret', required: true, visible_when: { auth_method: 'password' } },
    { id: 'private_key', name: '私钥内容', kind: 'secret', required: true, visible_when: { auth_method: 'key' } },
  ],
};

const withPickerI18n = (Story: React.ComponentType) => (
  <IntlProvider locale="zh" messages={pickerMessages}>
    <div className="min-h-screen bg-[var(--color-fill-1)] p-8">
      <div className="max-w-[720px]">
        <Story />
      </div>
    </div>
  </IntlProvider>
);

const meta: Meta<typeof CredentialPickerChrome> = {
  title: 'components/credential-picker',
  component: CredentialPickerChrome,
  decorators: [withPickerI18n],
  parameters: { layout: 'fullscreen' },
};

export default meta;

type Story = StoryObj<typeof CredentialPickerChrome>;

const StatefulPicker = (args: React.ComponentProps<typeof CredentialPickerChrome>) => {
  const [value, setValue] = useState(args.value ?? OPTIONS[0].value);
  return <CredentialPickerChrome {...args} value={value} onChange={setValue} />;
};

const Panel = ({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) => (
  <section className="mb-10">
    <h3 className="mb-1 text-sm font-semibold text-[var(--color-text-1)]">{title}</h3>
    {hint ? <p className="mb-3 text-xs text-[var(--color-text-3)]">{hint}</p> : null}
    {children}
  </section>
);

export const ReviewBoard: Story = {
  render: () => (
    <div>
      <p className="mb-6 text-sm leading-6 text-[var(--color-text-2)]">
        业务任务/实例原表单要引用仓库凭据时，在现有 Form 里用{' '}
        <code>CredentialPicker</code>
        （不是本页的 Chrome）：
        <code className="mx-1">{'<Form.Item name="credential_id"><CredentialPicker category="host" type="ssh" /></Form.Item>'}</code>
        。列表由组件请求系统管理，页面只收 credential_id。本页 Chrome 只用来看选用条样式，不打接口。
      </p>
      <Panel title="闭合态">
        <StatefulPicker options={OPTIONS} canAdd canView value={OPTIONS[0].value} />
      </Panel>
      <Panel title="展开态（有数据）" hint="底栏：+ 新增凭据、系统管理 ↗">
        <div className="relative min-h-[260px]">
          <CredentialPickerChrome options={OPTIONS} canAdd canView value={OPTIONS[0].value} dropdownOpen />
        </div>
      </Panel>
      <Panel title="展开态（空列表）">
        <div className="relative min-h-[200px]">
          <CredentialPickerChrome options={[]} canAdd canView dropdownOpen />
        </div>
      </Panel>
      <Panel title="无新增权限">
        <div className="relative min-h-[240px]">
          <CredentialPickerChrome options={OPTIONS} canAdd={false} canView dropdownOpen />
        </div>
      </Panel>
      <Panel title="无仓库查看权限">
        <div className="relative min-h-[240px]">
          <CredentialPickerChrome options={OPTIONS} canAdd canView={false} dropdownOpen />
        </div>
      </Panel>
    </div>
  ),
};

function QuickCreateCard() {
  const [form] = Form.useForm();
  React.useEffect(() => {
    form.setFieldsValue({
      category: 'host',
      type: 'ssh',
      group_id: 1,
      fields: { auth_method: 'password' },
    });
  }, [form]);
  return (
    <div className="mx-auto w-[520px] overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] shadow-md">
      <div className="flex items-center justify-between border-b border-[var(--color-border-2)] px-4 py-3">
        <h3 className="m-0 text-base font-semibold text-[var(--color-text-1)]">新建凭据并选用</h3>
        <span className="text-sm text-[var(--color-text-3)]">✕</span>
      </div>
      <div className="px-4 py-3">
        <CredentialQuickCreateForm
          form={form}
          types={[SSH_TYPE]}
          groups={[{ id: 1, name: '运维部' }]}
          lockedCategory
          lockedType
        />
      </div>
      <div className="flex justify-end gap-2 border-t border-[var(--color-border-2)] px-4 py-3">
        <Button>取消</Button>
        <Button type="primary">保存并选用</Button>
      </div>
    </div>
  );
}

export const QuickCreate: Story = {
  render: () => (
    <div>
      <p className="mb-6 text-sm text-[var(--color-text-2)]">
        调用方传入 category=host、type=ssh 时的快捷新建（分类/类型锁定）。这是弹窗内容，不是遮罩层。
      </p>
      <QuickCreateCard />
    </div>
  ),
};

export const Closed: Story = {
  render: (args) => <StatefulPicker {...args} />,
  args: {
    options: OPTIONS,
    canAdd: true,
    canView: true,
    value: OPTIONS[0].value,
  },
};

export const DropdownOpen: Story = {
  render: (args) => (
    <div className="relative min-h-[280px]">
      <StatefulPicker {...args} />
    </div>
  ),
  args: {
    options: OPTIONS,
    canAdd: true,
    canView: true,
    value: OPTIONS[0].value,
    dropdownOpen: true,
  },
};

export const ViewOnly: Story = {
  render: (args) => (
    <div className="relative min-h-[280px]">
      <StatefulPicker {...args} />
    </div>
  ),
  args: {
    options: OPTIONS,
    canAdd: false,
    canView: true,
    dropdownOpen: true,
  },
};

export const NoVaultLink: Story = {
  render: (args) => (
    <div className="relative min-h-[280px]">
      <StatefulPicker {...args} />
    </div>
  ),
  args: {
    options: OPTIONS,
    canAdd: false,
    canView: false,
    dropdownOpen: true,
  },
};
