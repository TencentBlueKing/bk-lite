'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { Button, Form, Select, Tooltip } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import Cookies from 'js-cookie';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import usePermissions from '@/hooks/usePermissions';
import { CREDENTIAL_CATEGORIES, CREDENTIAL_MENU_PATH } from './types';
import type { CredentialItem, CredentialTypeItem } from './types';
import { useCredentialPickerApi } from './api';
import { CredentialQuickCreateForm, inferredCategory } from './quick-create';

export { CREDENTIAL_MENU_PATH, CREDENTIAL_CATEGORIES };
export type { CredentialItem, CredentialTypeItem, CredentialFieldSchema } from './types';
export { renderCredentialFields, CredentialFieldsBlock } from './fields';
export { CredentialQuickCreateForm } from './quick-create';

export interface CredentialPickerChromeProps {
  value?: string;
  options: { label: string; value: string }[];
  loading?: boolean;
  canAdd: boolean;
  canView: boolean;
  onChange?: (credentialId: string | undefined) => void;
  onRefresh?: () => void;
  onAdd?: () => void;
  onOpenVault?: () => void;
  placeholder?: string;
  /** 仅预览用：钉住下拉，方便看底栏和选项。 */
  dropdownOpen?: boolean;
}

export const CredentialPickerChrome: React.FC<CredentialPickerChromeProps> = ({
  value,
  options,
  loading,
  canAdd,
  canView,
  onChange,
  onRefresh,
  onAdd,
  onOpenVault,
  placeholder,
  dropdownOpen,
}) => {
  const { t } = useTranslation();
  const addButton = (
    <Button
      type="link"
      size="small"
      icon={<PlusOutlined />}
      disabled={!canAdd}
      onClick={canAdd ? onAdd : undefined}
    >
      {t('system.credential.addCredential')}
    </Button>
  );

  return (
    <div className="flex w-full items-center gap-2">
      <Select
        className="min-w-0 flex-1"
        allowClear
        showSearch
        optionFilterProp="label"
        loading={loading}
        value={value}
        {...(dropdownOpen === undefined ? {} : { open: dropdownOpen })}
        getPopupContainer={(node) => node.parentElement || document.body}
        placeholder={placeholder || t('system.credential.selectPlaceholder')}
        options={options}
        onChange={(next) => onChange?.(next)}
        dropdownRender={(menu) => (
          <div>
            {menu}
            <div className="flex items-center justify-between border-t border-[var(--color-border)] px-2 py-1">
              {canAdd ? (
                addButton
              ) : (
                <Tooltip title={t('system.credential.noAddPermission')}>
                  <span>{addButton}</span>
                </Tooltip>
              )}
              {canView ? (
                <Button type="link" size="small" onClick={onOpenVault}>
                  {t('system.credential.openVault')}
                </Button>
              ) : null}
            </div>
          </div>
        )}
      />
      <Button type="text" icon={<ReloadOutlined />} loading={loading} onClick={onRefresh} />
    </div>
  );
};

export interface CredentialPickerProps {
  category?: string;
  type?: string;
  value?: string;
  onChange?: (credentialId: string | undefined) => void;
}

const CredentialPicker: React.FC<CredentialPickerProps> = ({ category, type, value, onChange }) => {
  const { t } = useTranslation();
  const { hasPermission } = usePermissions(CREDENTIAL_MENU_PATH);
  const canAdd = hasPermission(['Add']);
  const canView = hasPermission(['View']);
  const {
    listSelectableCredentials,
    listSelectableTypes,
    createCredential,
  } = useCredentialPickerApi();
  const [form] = Form.useForm();
  const [items, setItems] = useState<CredentialItem[]>([]);
  const [types, setTypes] = useState<CredentialTypeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const lockedType = Boolean(type);
  const lockedCategory = Boolean(category) || lockedType;
  const typeMismatch = Boolean(category && type && !types.some((item) => item.key === type && item.categories.includes(category)));

  const load = async () => {
    setLoading(true);
    try {
      const [nextItems, nextTypes] = await Promise.all([
        listSelectableCredentials({ category, type }),
        listSelectableTypes(category ? { category } : undefined),
      ]);
      setItems(nextItems);
      setTypes(nextTypes);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [category, type]);

  const typeNameByKey = useMemo(
    () => Object.fromEntries(types.map((item) => [item.key, item.name])),
    [types],
  );

  const options = items.map((item) => ({
    value: item.credential_id,
    label: `${item.name} - ${typeNameByKey[item.type] || item.type} (${item.credential_id})`,
  }));

  const openCreate = () => {
    const nextCategory = inferredCategory(types, category, type);
    const nextType = typeMismatch
      ? undefined
      : type || types.find((item) => !nextCategory || item.categories.includes(nextCategory))?.key;
    form.resetFields();
    form.setFieldsValue({
      category: nextCategory,
      type: nextType,
      group_id: Number(Cookies.get('current_team')),
      fields: {},
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const created = await createCredential({
        name: values.name,
        type: values.type,
        group_id: values.group_id,
        fields: values.fields || {},
      });
      setModalOpen(false);
      await load();
      onChange?.(created.credential_id);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <CredentialPickerChrome
        value={value}
        options={typeMismatch ? [] : options}
        loading={loading}
        canAdd={canAdd}
        canView={canView}
        onChange={onChange}
        onRefresh={() => void load()}
        onAdd={openCreate}
        onOpenVault={() => window.open(CREDENTIAL_MENU_PATH, '_blank')}
      />
      <OperateModal
        title={t('system.credential.quickCreateTitle')}
        open={modalOpen}
        confirmLoading={saving}
        okText={t('system.credential.saveAndSelect')}
        cancelText={t('common.cancel')}
        onOk={() => void handleSave()}
        onCancel={() => setModalOpen(false)}
        width={520}
      >
          <CredentialQuickCreateForm
            form={form}
            types={types}
            hideOrganization
            lockedCategory={lockedCategory}
            lockedType={lockedType}
            typeMismatch={typeMismatch}
          />
      </OperateModal>
    </>
  );
};

export default CredentialPicker;
