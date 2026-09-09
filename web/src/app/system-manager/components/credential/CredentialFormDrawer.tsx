'use client';

import React, { useEffect, useState } from 'react';
import { Form, Input, Select, Spin, Tag } from 'antd';
import ContentDrawer from '@/components/content-drawer';
import { renderFormFeedbackFooter } from '@/components/form-feedback-footer';
import GroupTreeSelect from '@/components/group-tree-select';
import { useTranslation } from '@/utils/i18n';
import type { CredentialGroupOption, CredentialItem, CredentialTypeItem } from '@/components/credential-picker/types';
import { CredentialFieldsBlock } from '@/components/credential-picker';

export type CredentialDrawerMode = 'create' | 'edit' | 'view';

interface CredentialFormDrawerProps {
  open: boolean;
  mode: CredentialDrawerMode;
  types: CredentialTypeItem[];
  groups: CredentialGroupOption[];
  lockedType?: string;
  record?: CredentialItem | null;
  loading?: boolean;
  onClose: () => void;
  onSubmit: (payload: { name: string; type: string; group_id: number; fields: Record<string, unknown> }) => Promise<void>;
}

const CredentialFormDrawer: React.FC<CredentialFormDrawerProps> = ({
  open,
  mode,
  types,
  groups,
  lockedType,
  record,
  loading = false,
  onClose,
  onSubmit,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const watchedType = Form.useWatch('type', form);
  const selectedType = types.find((item) => item.key === watchedType) || types.find((item) => item.key === lockedType);
  const readOnly = mode === 'view';
  const typeFixed = mode !== 'create' || Boolean(lockedType);

  useEffect(() => {
    if (!open) {
      return;
    }
    form.resetFields();
    form.setFieldsValue({
      name: record?.name,
      type: lockedType || record?.type || types[0]?.key,
      group_id: record?.group_id ?? groups[0]?.id,
      fields: record?.fields || {},
    });
  }, [open, record, lockedType, groups, types, form, mode]);

  const handleOk = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      await onSubmit({
        name: values.name,
        type: values.type,
        group_id: values.group_id,
        fields: values.fields || {},
      });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const typeOptionLabel = (item: CredentialTypeItem) => (
    `${item.name}（${item.key}）${item.is_builtin ? '' : ` · ${t('system.credential.custom')}`}`
  );

  const title = (() => {
    if (mode === 'create') {
      return t('system.credential.createCredential', '新建凭据');
    }
    const name = record?.name || '—';
    return mode === 'edit'
      ? t('system.credential.editCredentialTitle', '编辑凭据-{name}', { name })
      : t('system.credential.viewCredentialTitle', '查看凭据-{name}', { name });
  })();

  const secretPlaceholder = readOnly
    ? t('system.credential.secretSaved')
    : mode === 'edit'
      ? t('system.credential.secretLeaveBlank')
      : t('system.credential.enterSecret', '请输入密码');

  return (
    <ContentDrawer
      title={title}
      open={open}
      width={560}
      footer={readOnly ? null : (
        <div className="flex justify-end">
          {renderFormFeedbackFooter({
            confirmLoading: saving,
            confirmDisabled: loading,
            confirmText: mode === 'edit' ? t('system.credential.saveCredentialUpdate', '保存更新') : t('system.credential.saveCredential', '保存凭据'),
            cancelText: t('common.cancel'),
            primaryFirst: false,
            onCancel: onClose,
            onConfirm: () => void handleOk(),
          })}
        </div>
      )}
      onClose={onClose}
      content={(
        <Spin spinning={loading}>
          <Form form={form} layout="vertical" className="min-h-40">
            <Form.Item
              name="name"
              label={t('system.credential.credentialName', '凭据名称')}
              rules={[{ required: true, whitespace: true }]}
            >
              <Input
                disabled={readOnly}
                placeholder={mode === 'create' ? t('system.credential.credentialNamePlaceholder', '例如：生产 MySQL 只读') : undefined}
              />
            </Form.Item>
            <Form.Item
              name="group_id"
              label={t('system.credential.organizationBelong', '所属组织')}
              rules={[{ required: true }]}
            >
              <GroupTreeSelect
                multiple={false}
                mode="ownership"
                disabled={readOnly}
                showSearch
                placeholder={t('common.selectTip')}
              />
            </Form.Item>
            {typeFixed ? (
              <>
                <Form.Item
                  label={t('system.credential.credentialType', '凭据类型')}
                >
                  <Tag
                    bordered={false}
                    className="m-0 rounded px-2 py-0.5 font-medium text-[var(--color-text-2)] bg-[var(--color-fill-2)]"
                  >
                    {selectedType?.name || watchedType}
                  </Tag>
                </Form.Item>
                <Form.Item name="type" hidden rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </>
            ) : (
              <Form.Item name="type" label={t('system.credential.credentialType', '凭据类型')} rules={[{ required: true }]}>
                <Select
                  options={types.map((item) => ({
                    value: item.key,
                    label: typeOptionLabel(item),
                  }))}
                />
              </Form.Item>
            )}
            <div className="mt-1">
              {selectedType?.fields?.length ? (
                <CredentialFieldsBlock
                  key={selectedType.key}
                  fields={selectedType.fields}
                  form={form}
                  readOnly={readOnly}
                  secretPlaceholder={secretPlaceholder}
                />
              ) : selectedType ? (
                <p className="mb-0 text-xs text-[var(--color-text-3)]">
                  {t('system.credential.typeHasNoFields', '该类型尚未定义字段，请先到「凭据类型」页签设计字段。')}
                </p>
              ) : null}
            </div>
          </Form>
        </Spin>
      )}
    />
  );
};

export default CredentialFormDrawer;
