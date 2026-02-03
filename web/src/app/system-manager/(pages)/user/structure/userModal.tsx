'use client';

import React, { forwardRef, useImperativeHandle, useMemo } from 'react';
import { Input, Button, Form, Spin, Select, Radio, Alert } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { useTranslation } from '@/utils/i18n';
import { ZONEINFO_OPTIONS, LOCALE_OPTIONS } from '@/app/system-manager/constants/userDropdowns';
import RoleTransfer from '@/app/system-manager/components/user/roleTransfer';
import { useUserModalData } from '@/app/system-manager/hooks/useUserModalData';
import { transformTreeDataForSelect } from '@/app/system-manager/utils/userFormUtils';

interface ModalProps {
  onSuccess: () => void;
  treeData: TreeDataNode[];
}

interface ModalConfig {
  type: 'add' | 'edit';
  userId?: string;
  groupKeys?: number[];
}

export interface ModalRef {
  showModal: (config: ModalConfig) => void;
}

const UserModal = forwardRef<ModalRef, ModalProps>(({ onSuccess, treeData }, ref) => {
  const { t } = useTranslation();

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
    groupRules,
    organizationRoleIds,
    isSuperuser,
    setSelectedRoles,
    setIsSuperuser,
    showModal,
    handleCancel,
    handleConfirm,
    handleGroupChange,
    handleChangeRule,
  } = useUserModalData();

  useImperativeHandle(ref, () => ({
    showModal,
  }));

  const filteredTreeData = useMemo(
    () => (treeData ? transformTreeDataForSelect(treeData) : []),
    [treeData]
  );

  const handleRoleChange = (newKeys: number[]) => {
    setSelectedRoles(newKeys);
    formRef.current?.setFieldsValue({ roles: newKeys });
  };

  const handleSuperuserChange = (value: boolean) => {
    setIsSuperuser(value);
    formRef.current?.setFieldsValue({ is_superuser: value });
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
            <Input placeholder={`${t('common.inputMsg')}${t('system.user.form.email')}`} />
          </Form.Item>
          <Form.Item
            name="lastName"
            label={t('system.user.form.lastName')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input placeholder={`${t('common.inputMsg')}${t('system.user.form.lastName')}`} />
          </Form.Item>
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
            name="groups"
            label={t('system.user.form.group')}
            rules={[{ required: !isSuperuser, message: t('common.inputRequired') }]}
          >
            <RoleTransfer
              mode="group"
              enableSubGroupSelect={true}
              groupRules={groupRules}
              treeData={filteredTreeData}
              selectedKeys={selectedGroups}
              onChange={handleGroupChange}
              onChangeRule={handleChangeRule}
            />
          </Form.Item>
          <Form.Item
            name="roles"
            label={t('system.user.form.role')}
            tooltip={t('system.user.form.rolePermissionTip')}
            rules={[{ required: !isSuperuser, message: t('common.inputRequired') }]}
          >
            <Form.Item name="is_superuser" style={{ marginBottom: 8 }}>
              <Radio.Group onChange={(e) => handleSuperuserChange(e.target.value)}>
                <Radio value={false}>{t('system.user.form.normalUser')}</Radio>
                <Radio value={true}>{t('system.user.form.superuser')}</Radio>
              </Radio.Group>
            </Form.Item>
            {!isSuperuser ? (
              <RoleTransfer
                groupRules={groupRules}
                treeData={roleTreeData}
                selectedKeys={selectedRoles}
                loading={roleLoading}
                forceOrganizationRole={false}
                organizationRoleIds={organizationRoleIds}
                onChange={handleRoleChange}
              />
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
