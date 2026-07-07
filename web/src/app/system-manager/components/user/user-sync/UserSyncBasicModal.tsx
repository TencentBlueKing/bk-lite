import React, { useEffect } from 'react';
import { Button, Form, Input, Select } from 'antd';

import OperateModal from '@/components/operate-modal';
import type { AvailableInstance, UserSyncSource, UserSyncSourceBasicFormValues } from '@/app/system-manager/types/user-sync';
import { formatIntegrationInstanceDisplayName } from '@/app/system-manager/utils/integrationCenter';

interface UserSyncBasicModalProps {
  open: boolean;
  source: UserSyncSource | null;
  loading: boolean;
  availableInstances: AvailableInstance[];
  t: (key: string, fallback?: string) => string;
  onClose: () => void;
  onSubmit: (values: UserSyncSourceBasicFormValues) => void;
}

const UserSyncBasicModal: React.FC<UserSyncBasicModalProps> = ({
  open,
  source,
  loading,
  availableInstances,
  t,
  onClose,
  onSubmit,
}) => {
  const [form] = Form.useForm<UserSyncSourceBasicFormValues>();

  useEffect(() => {
    if (!open || !source) return;
    form.setFieldsValue({
      name: source.name,
      integration_instance: source.integration_instance,
      description: source.description,
      root_group_name: source.root_group_name,
    });
  }, [open, source, form]);

  const instanceOptions = availableInstances.map((inst) => ({
    value: inst.id,
    label: formatIntegrationInstanceDisplayName(inst, t),
  }));

  const handleSubmit = async () => {
    try {
      await form.validateFields();
    } catch {
      return;
    }
    onSubmit(form.getFieldsValue(true) as UserSyncSourceBasicFormValues);
  };

  return (
    <OperateModal
      title={t('system.user.userSyncPage.editSource')}
      open={open}
      onCancel={onClose}
      width={720}
      footer={(
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} disabled={loading}>
            {t('common.cancel')}
          </Button>
          <Button type="primary" onClick={handleSubmit} loading={loading}>
            {t('common.save')}
          </Button>
        </div>
      )}
      destroyOnClose
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label={t('common.name')}
          rules={[{ required: true, whitespace: true }]}
        >
          <Input placeholder={t('common.inputMsg')} />
        </Form.Item>
        <Form.Item
          name="integration_instance"
          label={t('system.user.userSyncPage.integrationSystem')}
          rules={[{ required: true }]}
        >
          <Select
            disabled
            options={instanceOptions}
            placeholder={t('system.user.userSyncPage.integrationSystemPlaceholder')}
          />
        </Form.Item>
        <Form.Item
          name="root_group_name"
          label={t('system.user.userSyncPage.rootGroupNameLabel')}
          tooltip={t('system.user.userSyncPage.rootGroupNameImmutable')}
          rules={[{ required: true, whitespace: true }]}
        >
          <Input disabled />
        </Form.Item>
        <Form.Item name="description" label={t('system.user.userSyncPage.description')}>
          <Input.TextArea rows={4} placeholder={t('common.inputMsg')} />
        </Form.Item>
      </Form>
      {source ? (
        <div className="mt-2 text-[12px] text-[var(--color-text-3)]">
          {source.integration_instance_name} · {t('system.user.userSyncPage.rootGroupNameLabel')}：{source.root_group_name}
        </div>
      ) : null}
    </OperateModal>
  );
};

export default UserSyncBasicModal;
