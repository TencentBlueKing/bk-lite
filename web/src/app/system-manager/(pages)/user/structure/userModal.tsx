'use client';

import React, { forwardRef, useEffect, useImperativeHandle, useMemo, useState } from 'react';
import { Input, Button, Form, Spin, Select, Radio, Alert, Space, DatePicker } from 'antd';
import { EditOutlined, CheckOutlined, CloseOutlined } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { ZONEINFO_OPTIONS, LOCALE_OPTIONS } from '@/app/system-manager/constants/userDropdowns';
import RoleTransfer from '@/app/system-manager/components/user/roleTransfer';
import { useUserModalData } from '@/app/system-manager/hooks/useUserModalData';
import {
  filterSyncedGroupsForLocalUser,
  flattenTreeSelectNodes,
  transformTreeDataForSelect,
} from '@/app/system-manager/utils/userFormUtils';
import type { TreeSelectNode } from '@/app/system-manager/utils/userFormUtils';

const EMPTY_GROUP_IDS: React.Key[] = [];

interface CustomFieldDefinition {
  key: string;
  name: string;
  field_type: 'text' | 'number' | 'date';
  description?: string;
  is_enabled: boolean;
}

interface ModalProps {
  onSuccess: () => void;
  treeData: TreeDataNode[];
}

interface ModalConfig {
  type: 'add' | 'edit';
  userId?: string;
  groupKeys?: React.Key[];
  groupTreeData?: TreeSelectNode[];
}

export interface ModalRef {
  showModal: (config: ModalConfig) => void;
}

const UserModal = forwardRef<ModalRef, ModalProps>(({ onSuccess, treeData }, ref) => {
  const { t } = useTranslation();
  const { get } = useApiClient();
  const [customFields, setCustomFields] = useState<CustomFieldDefinition[]>([]);
  const [managerUsers, setManagerUsers] = useState<Array<{ id: string | number; username: string; display_name?: string }>>([]);
  const [managerLoading, setManagerLoading] = useState(false);

  const {
    formRef,
    visible,
    loading,
    roleLoading,
    isSubmitting,
    type,
    roleTreeData,
    selectedGroups,
    selectedRoles,
    personalRoleIds,
    groupRules,
    organizationRoleIds,
    organizationRoleSourceMap,
    isSuperuser,
    isSyncedUser,
    currentUserId,
    showModal,
    handleCancel,
    handleConfirm,
    handleGroupChange,
    handleRoleChange,
    handleSuperuserChange,
    handleChangeRule,
    sensitiveBehavior,
  } = useUserModalData();

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    get('/system_mgmt/user_field/search/')
      .then((rows: CustomFieldDefinition[]) => {
        if (!cancelled) setCustomFields(Array.isArray(rows) ? rows : []);
      })
      .catch(() => {
        if (!cancelled) setCustomFields([]);
      });
    setManagerLoading(true);
    get('/system_mgmt/user/user_id_all/')
      .then((rows: Array<{ id: string | number; username: string; display_name?: string }>) => {
        if (!cancelled) setManagerUsers(Array.isArray(rows) ? rows : []);
      })
      .catch(() => {
        if (!cancelled) setManagerUsers([]);
      })
      .finally(() => {
        if (!cancelled) setManagerLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [get, visible]);

  const filteredTreeData = useMemo(
    () => (treeData ? transformTreeDataForSelect(treeData) : []),
    [treeData]
  );

  const historicalSyncedGroupIds = useMemo(() => {
    const groupMap = new Map(flattenTreeSelectNodes(filteredTreeData).map((node) => [String(node.key), node]));
    return selectedGroups.filter((groupId) => {
      const group = groupMap.get(String(groupId));
      return group?.syncSource !== null && group?.syncSource !== undefined;
    });
  }, [filteredTreeData, selectedGroups]);

  const syncedGroupIdsKey = type === 'edit'
    ? historicalSyncedGroupIds.map(String).slice().sort().join('\0')
    : '';
  const selectableGroupTreeData = useMemo(
    () => filterSyncedGroupsForLocalUser(
      filteredTreeData,
      type === 'edit' ? historicalSyncedGroupIds : EMPTY_GROUP_IDS
    ),
    [filteredTreeData, type, syncedGroupIdsKey]
  );

  const isGroupSelectionLocked = isSyncedUser || historicalSyncedGroupIds.length > 0;

  useImperativeHandle(ref, () => ({
    showModal: (config) => showModal({
      ...config,
      groupTreeData: filteredTreeData,
    }),
  }), [filteredTreeData, showModal]);

  const renderSensitiveInput = (fieldName: string, placeholder: string) => {
    if (type === 'add') {
      return <Input placeholder={placeholder} />;
    }

    const state = sensitiveBehavior.fieldsState[fieldName];
    const mode = state?.mode;
    const isEditing = state?.isEditing;

    if (mode !== 'overwrite') {
      return <Input placeholder={placeholder} />;
    }

    return (
      <Input
        placeholder={placeholder}
        disabled={!isEditing}
        suffix={
          <Space>
            {!isEditing ? (
              <EditOutlined
                style={{ cursor: 'pointer', color: '#3a84ff' }}
                onClick={() => sensitiveBehavior.handleEditClick(fieldName)}
              />
            ) : (
              <>
                <CheckOutlined
                  style={{ cursor: 'pointer', color: '#2dcb56' }}
                  onClick={() => sensitiveBehavior.handleConfirmEdit(fieldName)}
                />
                <CloseOutlined
                  style={{ cursor: 'pointer', color: '#ea3636' }}
                  onClick={() => sensitiveBehavior.handleCancelEdit(fieldName)}
                />
              </>
            )}
          </Space>
        }
      />
    );
  };

  return (
    <OperateModal
      title={type === 'add' ? t('common.add') : t('common.edit')}
      width={860}
      open={visible}
      onCancel={handleCancel}
      footer={[
        <Button key="cancel" onClick={handleCancel}>
          {t('common.cancel')}
        </Button>,
        <Button
          key="submit"
          type="primary"
          onClick={() => handleConfirm(onSuccess)}
          loading={isSubmitting || loading}
        >
          {t('common.confirm')}
        </Button>,
      ]}
    >
      <Spin spinning={loading}>
        <Form ref={formRef} layout="vertical">
          {type === 'edit' && isSyncedUser && (
            <Alert
              message={t('system.user.form.syncedContactOverwriteTip')}
              type="info"
              showIcon
              className="mb-4"
            />
          )}
          <Form.Item
            name="username"
            label={t('system.user.form.username')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input
              placeholder={`${t('common.inputMsg')}${t('system.user.form.username')}`}
              disabled={type === 'edit'}
            />
          </Form.Item>
          <Form.Item
            name="email"
            label={t('system.user.form.email')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            {renderSensitiveInput('email', `${t('common.inputMsg')}${t('system.user.form.email')}`)}
          </Form.Item>
          <Form.Item
            name="phone"
            label={t('system.user.form.phone')}
          >
            {renderSensitiveInput('phone', `${t('common.inputMsg')}${t('system.user.form.phone')}`)}
          </Form.Item>
          <Form.Item
            name="lastName"
            label={t('system.user.form.lastName')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input placeholder={`${t('common.inputMsg')}${t('system.user.form.lastName')}`} disabled={type === 'edit' && isSyncedUser} />
          </Form.Item>
          <Form.Item
            name="manager_username"
            label={t('system.user.form.manager')}
            getValueProps={(value) => ({ value: value || undefined })}
          >
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              loading={managerLoading}
              placeholder={t('system.user.form.managerPlaceholder')}
              options={managerUsers
                .filter((user) => type !== 'edit' || String(user.id) !== String(currentUserId))
                .map((user) => ({
                  value: user.username,
                  label: `${user.display_name || user.username} (${user.username})`,
                }))}
            />
          </Form.Item>
          <Form.Item name="employment_status" label={t('system.user.form.employmentStatus')} initialValue="unspecified">
            <Select
              options={[
                { value: 'unspecified', label: t('system.user.form.employmentUnspecified') },
                { value: 'employed', label: t('system.user.form.employmentEmployed') },
                { value: 'resigned', label: t('system.user.form.employmentResigned') },
              ]}
            />
          </Form.Item>
          <Form.Item name="job_title" label={t('system.user.form.jobTitle')}>
            <Input />
          </Form.Item>
          <Form.Item name="job_level" label={t('system.user.form.jobLevel')}>
            <Input />
          </Form.Item>
          <Form.Item name="employee_no" label={t('system.user.form.employeeNo')}>
            <Input />
          </Form.Item>
          <Form.Item name="account_expires_at" label={t('system.user.form.accountExpiresAt')} extra={t('system.user.form.accountPermanent')}>
            <DatePicker showTime className="w-full" />
          </Form.Item>
          {customFields.map((field) => (
            <Form.Item key={field.key} name={['custom_fields', field.key]} label={field.name} extra={field.description}>
              {field.field_type === 'date' ? (
                <DatePicker className="w-full" disabled={!field.is_enabled} />
              ) : (
                <Input disabled={!field.is_enabled} />
              )}
            </Form.Item>
          ))}
          <Form.Item
            name="zoneinfo"
            label={t('system.user.form.zoneinfo')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Select
              showSearch
              placeholder={`${t('common.selectMsg')}${t('system.user.form.zoneinfo')}`}
            >
              {ZONEINFO_OPTIONS.map((option) => (
                <Select.Option key={option.value} value={option.value}>
                  {t(option.label)}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            name="locale"
            label={t('system.user.form.locale')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Select placeholder={`${t('common.selectMsg')}${t('system.user.form.locale')}`}>
              {LOCALE_OPTIONS.map((option) => (
                <Select.Option key={option.value} value={option.value}>
                  {t(option.label)}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            label={t('common.organization')}
            required={!isSuperuser}
          >
            {visible && (type !== 'edit' || !loading) ? (
              <RoleTransfer
                mode="group"
                enableSubGroupSelect={true}
                groupRules={groupRules}
                treeData={selectableGroupTreeData}
                selectedKeys={selectedGroups}
                onChange={handleGroupChange}
                onChangeRule={handleChangeRule}
                disabled={isGroupSelectionLocked}
              />
            ) : null}
          </Form.Item>
          <Form.Item
            label={t('system.user.form.role')}
            tooltip={t('system.user.form.rolePermissionTip')}
            required={type === 'edit' && !isSuperuser}
          >
            <Form.Item name="is_superuser" style={{ marginBottom: 8 }}>
                <Radio.Group onChange={(e) => handleSuperuserChange(e.target.value)}>
                <Radio value={false}>{t('system.user.form.normalUser')}</Radio>
                <Radio value={true}>{t('system.user.form.superuser')}</Radio>
              </Radio.Group>
            </Form.Item>
            {!isSuperuser ? (
              visible ? (
                <RoleTransfer
                  groupRules={groupRules}
                  treeData={roleTreeData}
                  selectedKeys={selectedRoles}
                  personalRoleIds={personalRoleIds}
                  loading={roleLoading}
                  forceOrganizationRole={false}
                  organizationRoleIds={organizationRoleIds}
                  organizationRoleSourceMap={organizationRoleSourceMap}
                  onChange={handleRoleChange}
                />
              ) : null
            ) : (
              <div>{t('system.user.form.superuser')}</div>
            )}
            {isSuperuser && (
              <Alert
                message={t('system.user.form.superuserTip')}
                type="info"
                showIcon
                style={{ marginTop: 8 }}
              />
            )}
          </Form.Item>
        </Form>
      </Spin>
    </OperateModal>
  );
});

UserModal.displayName = 'UserModal';
export default UserModal;
