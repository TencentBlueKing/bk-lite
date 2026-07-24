import type { Meta, StoryObj } from '@storybook/nextjs';
import { Form } from 'antd';
import { useEffect, useState } from 'react';
import { IntlProvider } from 'react-intl';
import { expect, within } from 'storybook/test';
import NetworkWhitelistFormModal, {
  type NetworkWhitelistEntryType,
  type NetworkWhitelistFormValues,
} from '@/app/system-manager/components/network-whitelist-form-modal';
import zhCommon from '@/locales/zh.json';
import zhSystemManager from '@/app/system-manager/locales/zh.json';

type LocaleJson = Record<string, unknown>;

const flatten = (obj: LocaleJson, prefix = '', out: Record<string, string> = {}) => {
  Object.entries(obj).forEach(([keyPart, value]) => {
    const key = prefix ? `${prefix}.${keyPart}` : keyPart;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      flatten(value as LocaleJson, key, out);
    } else {
      out[key] = String(value);
    }
  });
  return out;
};

const messages = {
  ...flatten(zhCommon as LocaleJson),
  ...flatten(zhSystemManager as LocaleJson),
};

interface StoryProps {
  editing: boolean;
  initialType: NetworkWhitelistEntryType;
}

const NetworkWhitelistModalStory = ({ editing, initialType }: StoryProps) => {
  const [form] = Form.useForm<NetworkWhitelistFormValues>();
  const [entryType, setEntryType] = useState(initialType);

  useEffect(() => {
    setEntryType(initialType);
    form.setFieldsValue({
      enabled: true,
      network: initialType === 'cidr' && editing ? '10.11.73.0/24' : undefined,
      domain_name: initialType === 'domain' && editing ? 'corp-wecom.example.com' : undefined,
      remark: editing ? '企业微信私有化部署出口' : undefined,
    });
  }, [editing, form, initialType]);

  return (
    // @ts-expect-error react-intl type incompatibility with React 19
    <IntlProvider locale="zh" messages={messages}>
      <div style={{ minHeight: 680 }}>
        <NetworkWhitelistFormModal
          open
          editing={editing}
          entryType={entryType}
          form={form}
          onEntryTypeChange={(next) => {
            setEntryType(next);
            form.setFieldsValue({
              network: next === 'cidr' ? form.getFieldValue('network') : undefined,
              domain_name: next === 'domain' ? form.getFieldValue('domain_name') : undefined,
            });
          }}
          onSubmit={() => {}}
          onCancel={() => {}}
        />
      </div>
    </IntlProvider>
  );
};

const meta = {
  title: 'System Manager/Settings/NetworkWhitelistFormModal',
  component: NetworkWhitelistModalStory,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof NetworkWhitelistModalStory>;

export default meta;
type Story = StoryObj<typeof meta>;

export const AddNetwork: Story = {
  args: { editing: false, initialType: 'cidr' },
  play: async () => {
    const dialog = await within(document.body).findByRole('dialog', { name: /新增白名单/ });
    await expect(within(dialog).getByText('保存后不可变更')).toBeInTheDocument();
    expect(dialog.querySelector('.ant-segmented')).not.toBeNull();
    await expect(within(dialog).getByText('选填')).toBeInTheDocument();
  },
};

export const AddDomain: Story = {
  args: { editing: false, initialType: 'domain' },
};

export const EditDomain: Story = {
  args: { editing: true, initialType: 'domain' },
  play: async () => {
    const dialog = await within(document.body).findByRole('dialog', { name: /编辑白名单/ });
    expect(dialog.querySelector('.ant-segmented')).toBeNull();
    await expect(within(dialog).getByDisplayValue('corp-wecom.example.com')).toBeInTheDocument();
  },
};
