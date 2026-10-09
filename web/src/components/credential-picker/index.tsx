'use client';

import React, { useEffect, useState } from 'react';
import { Button, Form, Select, Tooltip } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import Cookies from 'js-cookie';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import { CREDENTIAL_CATEGORIES, CREDENTIAL_MENU_PATH } from './types';
import type { CredentialItem, CredentialTypeItem } from './types';
import { useCredentialPickerApi } from './api';
import { CredentialQuickCreateForm, inferredCategory } from './quick-create';
import { normalizeCredentialFieldValues } from './normalizeFields';
import { buildCredentialVaultUrl } from './vaultLocate';

export { CREDENTIAL_MENU_PATH, CREDENTIAL_CATEGORIES };
export type { CredentialItem, CredentialTypeItem, CredentialFieldSchema } from './types';
export { renderCredentialFields, CredentialFieldsBlock } from './fields';
export { CredentialQuickCreateForm } from './quick-create';

export interface CredentialPickerChromeProps {
  value?: string;
  options: { label: string; value: string; disabled?: boolean }[];
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
        value={options.some((option) => option.value === value) ? value : undefined}
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

export interface CredentialBoundOption {
  credentialId: string;
  name: string;
  unavailable?: boolean;
}

export interface CredentialPickerProps {
  category?: string;
  type?: string;
  /** 多个内置类型按 category + type 分别请求后合并。快捷创建默认第一个。 */
  types?: string[];
  /** 限定 SNMP 版本。2 接受 v2/v2c，3 只接受 v3。 */
  snmpVersion?: 2 | 3;
  boundOption?: CredentialBoundOption;
  /** 限定 SSH 使用方支持的认证方式，同时约束快捷创建。 */
  sshAuthMethod?: 'password' | 'key';
  value?: string;
  onChange?: (credentialId: string | undefined) => void;
  onNamesResolved?: (credentials: { credential_id: string; name: string }[]) => void;
}

const CredentialPicker: React.FC<CredentialPickerProps> = ({
  category,
  type,
  types: typeList,
  snmpVersion,
  boundOption,
  sshAuthMethod,
  value,
  onChange,
  onNamesResolved,
}) => {
  const { t } = useTranslation();
  const [permissions, setPermissions] = useState<string[]>([]);
  const canAdd = permissions.includes('Add');
  const canView = permissions.includes('View');
  const {
    listSelectableCredentials,
    listSelectableTypes,
    createCredential,
    getCredentialPermissions,
  } = useCredentialPickerApi();
  const [form] = Form.useForm();
  const [items, setItems] = useState<CredentialItem[]>([]);
  const [types, setTypes] = useState<CredentialTypeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const requestedTypes = typeList?.length ? typeList : (type ? [type] : []);
  const primaryType = requestedTypes[0] || type;
  const lockedType = Boolean(primaryType);
  const lockedCategory = Boolean(category) || lockedType;
  const typeMismatch = Boolean(category && primaryType && !types.some((item) => item.key === primaryType && item.categories.includes(category)));

  const load = async () => {
    setLoading(true);
    setPermissions([]);
    try {
      const itemGroups = await Promise.all(
        (requestedTypes.length ? requestedTypes : [undefined]).map((itemType) =>
          listSelectableCredentials({ category, type: itemType })
        )
      );
      const merged = new Map<string, CredentialItem>();
      itemGroups.flat().forEach((item) => merged.set(item.credential_id, item));
      const nextItems = Array.from(merged.values());
      const [nextTypes, nextPermissions] = await Promise.all([
        listSelectableTypes(category ? { category } : undefined),
        getCredentialPermissions(),
      ]);
      setItems(nextItems);
      setTypes(nextTypes);
      setPermissions(nextPermissions);
      onNamesResolved?.(nextItems.map(({ credential_id, name }) => ({ credential_id, name })));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [category, type, typeList?.join('|'), snmpVersion]);

  const options = items
    .filter((item) => !sshAuthMethod || item.type !== 'ssh' || item.fields.auth_method === sshAuthMethod)
    .filter((item) => matchesSnmpVersion(item, snmpVersion))
    .map((item) => ({
      value: item.credential_id,
      label: item.name,
    }));
  if (boundOption?.credentialId && !options.some((option) => option.value === boundOption.credentialId)) {
    options.unshift({
      value: boundOption.credentialId,
      label: boundOption.name || boundOption.credentialId,
      disabled: Boolean(boundOption.unavailable),
    } as { value: string; label: string; disabled?: boolean });
  }

  const openCreate = () => {
    const nextCategory = inferredCategory(types, category, type);
    const nextType = typeMismatch
      ? undefined
      : primaryType || types.find((item) => !nextCategory || item.categories.includes(nextCategory))?.key;
    form.resetFields();
    form.setFieldsValue({
      category: nextCategory,
      type: nextType,
      group_id: Number(Cookies.get('current_team')),
      fields: nextType === 'ssh' && sshAuthMethod ? { auth_method: sshAuthMethod } : {},
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
        fields: normalizeCredentialFieldValues(
          types.find((item) => item.key === values.type)?.fields || [],
          values.fields,
        ),
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
        onOpenVault={() => window.open(buildCredentialVaultUrl(category, type), '_blank')}
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
            types={sshAuthMethod ? types.map((item) => item.key === 'ssh' ? {
              ...item,
              fields: item.fields.map((field) => field.id === 'auth_method'
                ? { ...field, values: [sshAuthMethod], default: sshAuthMethod }
                : field),
            } : item) : types}
            hideOrganization
            lockedCategory={lockedCategory}
            lockedType={lockedType}
            typeMismatch={typeMismatch}
          />
      </OperateModal>
    </>
  );
};

function matchesSnmpVersion(item: CredentialItem, snmpVersion?: 2 | 3) {
  if (!snmpVersion || item.type !== 'snmp') return true;
  const version = String(item.fields?.version || '');
  if (snmpVersion === 2) return version === 'v2' || version === 'v2c';
  return version === 'v3';
}

export default CredentialPicker;
