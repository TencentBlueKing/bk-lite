import React, { useState } from 'react';
import { Button, Divider, Form, Input, Select } from 'antd';
import { ExportOutlined, ReloadOutlined } from '@ant-design/icons';
import type { FormInstance } from 'antd';

import GroupTreeSelect from '@/components/group-tree-select';
import OperateModal from '@/components/operate-modal';
import type {
  AvailableInstance,
  IMNotificationChannel,
  IMNotificationChannelPayload,
} from '@/app/system-manager/types/im-notification';
import { formatIntegrationInstanceDisplayName } from '@/app/system-manager/utils/integrationCenter';
import { getImNotificationUnavailableEditingInstance } from '@/app/system-manager/utils/imNotificationUtils';
import NotificationTagSelect, { NotificationTagOption } from '@/app/system-manager/components/channel/NotificationTagSelect';

export type IMNotificationChannelFormValues = IMNotificationChannelPayload;

interface AccountAssociationOption {
  id: number;
  name: string;
  integration_instance_id: number;
  integration_instance_name: string;
}

function AccountAssociationField({
  value,
  onChange,
  options,
  loading,
  onRefresh,
  onManage,
  placeholder,
  manageLabel,
}: {
  value?: number | null;
  onChange?: (value: number | null) => void;
  options: AccountAssociationOption[];
  loading?: boolean;
  onRefresh?: () => void;
  onManage?: () => void;
  placeholder?: string;
  manageLabel?: string;
}) {
  return (
    <div className="flex items-start gap-2">
      <Select
        className="min-w-0 flex-1"
        allowClear
        placeholder={placeholder}
        value={value ?? undefined}
        options={options.map((item) => ({
          value: item.id,
          label: `${item.name}（${item.integration_instance_name}）`,
        }))}
        onChange={(next) => onChange?.(next ?? null)}
        dropdownRender={(menu) => (
          <>
            {menu}
            <Divider style={{ margin: '8px 0' }} />
            <div className="px-2 pb-1">
              <Button
                type="link"
                size="small"
                icon={<ExportOutlined />}
                onMouseDown={(event) => event.preventDefault()}
                onClick={onManage}
              >
                {manageLabel}
              </Button>
            </div>
          </>
        )}
      />
      <Button icon={<ReloadOutlined />} loading={loading} onClick={onRefresh} />
    </div>
  );
}

interface IMNotificationConfigModalProps {
  open: boolean;
  editing: IMNotificationChannel | null;
  loading: boolean;
  form: FormInstance<IMNotificationChannelFormValues>;
  availableInstances: AvailableInstance[];
  associationOptions: AccountAssociationOption[];
  tagOptions: NotificationTagOption[];
  t: (key: string, defaultMessage?: string, values?: Record<string, string | number>) => string;
  onRefreshOptions: () => Promise<AccountAssociationOption[]>;
  onOk: () => void;
  onCancel: () => void;
}

const IMNotificationConfigModal: React.FC<IMNotificationConfigModalProps> = ({
  open,
  editing,
  loading,
  form,
  availableInstances,
  associationOptions,
  tagOptions,
  t,
  onRefreshOptions,
  onOk,
  onCancel,
}) => {
  const [refreshingOptions, setRefreshingOptions] = useState(false);
  const instanceId = Form.useWatch('integration_instance', form);
  const filteredAssociations = associationOptions.filter((item) => item.integration_instance_id === instanceId);
  const unavailableEditingInstance = getImNotificationUnavailableEditingInstance(availableInstances, editing);
  const integrationInstanceOptions = [
    ...(unavailableEditingInstance ? [{
      value: unavailableEditingInstance.id,
      label: `${formatIntegrationInstanceDisplayName(unavailableEditingInstance)} (${t('system.channel.imNotificationPage.currentInstanceUnavailable')})`,
      disabled: true,
    }] : []),
    ...availableInstances.map((instance) => ({
      value: instance.id,
      label: formatIntegrationInstanceDisplayName(instance),
    })),
  ];

  const refreshOptions = async () => {
    setRefreshingOptions(true);
    try {
      const nextOptions = await onRefreshOptions();
      const current = form.getFieldValue('account_association');
      const stillListed = (nextOptions || []).some((item) => item.id === current && item.integration_instance_id === instanceId);
      if (current && !stillListed) {
        form.setFieldValue('account_association', null);
      }
    } finally {
      setRefreshingOptions(false);
    }
  };

  const openManage = () => {
    const params = new URLSearchParams({ tab: 'account_association' });
    const selected = form.getFieldValue('account_association');
    if (selected) {
      const selectedOption = associationOptions.find((item) => item.id === selected);
      if (selectedOption?.integration_instance_id) {
        params.set('instanceId', String(selectedOption.integration_instance_id));
      }
    } else if (instanceId) {
      params.set('instanceId', String(instanceId));
      params.set('create', '1');
    } else {
      const providerKeys = Array.from(new Set(availableInstances.map((item) => item.provider_key).filter(Boolean)));
      const onlyProvider = providerKeys.length === 1 ? providerKeys[0] : '';
      if (onlyProvider) {
        params.set('provider', onlyProvider);
      }
    }
    window.open(`/system-manager/user/user-sync?${params.toString()}`, '_blank', 'noopener,noreferrer');
  };

  return (
    <OperateModal
    title={editing ? t('common.edit') : t('common.add')}
    open={open}
    onOk={onOk}
    onCancel={onCancel}
    confirmLoading={loading}
    width={640}
  >
    <Form form={form} layout="vertical">
      <div className="mb-6">
        <div className="mb-2 text-[16px] font-semibold text-[var(--color-text-1)]">
          {t('system.channel.imNotificationPage.basicInfoTitle')}
        </div>
        <div className="mb-5 text-[13px] text-[var(--color-text-3)]">
          {t('system.channel.imNotificationPage.basicInfoDesc')}
        </div>
        <Form.Item name="name" label={t('system.channel.imNotificationPage.name')} rules={[{ required: true, whitespace: true }]}>
          <Input placeholder={t('system.channel.imNotificationPage.namePlaceholder')} />
        </Form.Item>
        <Form.Item
          name="integration_instance"
          label={t('system.channel.imNotificationPage.integrationInstance')}
          rules={[{ required: true }]}
        >
          <Select
            placeholder={t('system.channel.imNotificationPage.integrationInstancePlaceholder')}
            options={integrationInstanceOptions}
            onChange={() => form.setFieldValue('account_association', null)}
          />
        </Form.Item>
        <Form.Item
          name="account_association"
          label={t('system.channel.imNotificationPage.accountAssociation', '账号关联')}
          tooltip={t(
            'system.channel.imNotificationPage.accountAssociationTooltip',
            '发送时按该账号关联的匹配规则，以平台账号字段确定接收人的 IM 账号。',
          )}
          rules={[{
            required: true,
            message: `${t('common.selectMsg')}${t('system.channel.imNotificationPage.accountAssociation', '账号关联')}`,
          }]}
        >
          <AccountAssociationField
            options={filteredAssociations}
            loading={refreshingOptions}
            onRefresh={refreshOptions}
            onManage={openManage}
            placeholder={t('system.channel.imNotificationPage.accountAssociationPlaceholder', '选择账号关联')}
            manageLabel={t('system.channel.imNotificationPage.manageAccountAssociation', '管理账号关联')}
          />
        </Form.Item>
        <Form.Item
          name="team"
          label={t('common.organization')}
          rules={[{ required: true, type: 'array', min: 1, message: `${t('common.selectMsg')}${t('common.organization')}` }]}
        >
          <GroupTreeSelect
            placeholder={`${t('common.selectMsg')}${t('common.organization')}`}
            multiple
            mode="ownership"
          />
        </Form.Item>
        <Form.Item name="tag" label={t('system.channel.settings.tag')}>
          <NotificationTagSelect
            options={tagOptions}
            placeholder={`${t('common.selectMsg')}${t('system.channel.settings.tag')}`}
          />
        </Form.Item>
        <Form.Item name="description" label={t('system.channel.imNotificationPage.description')}>
          <Input.TextArea rows={3} placeholder={t('system.channel.imNotificationPage.descriptionPlaceholder')} />
        </Form.Item>
      </div>
    </Form>
    </OperateModal>
  );
};

export default IMNotificationConfigModal;
