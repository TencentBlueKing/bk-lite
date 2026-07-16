import React, { useState, useRef, forwardRef, useImperativeHandle, useEffect } from 'react';
import { Input, Form, message, Switch, Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import OperateFormModal from '@/components/operate-form-modal';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import RoleTransfer from '@/components/system-manager-role-transfer';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { processRoleTreeData } from './role-tree-utils';

interface ModalProps {
  onSuccess: () => void;
  clientData: Array<{ name?: string | null }>;
  fetchGroupDetailWithRolesAction: (params: { group_id: string | number }) => Promise<{
    allow_inherit_roles?: boolean;
    own_role_ids?: number[];
    inherited_role_ids?: number[];
    inherited_role_source_map?: Record<string, string>;
  }>;
  fetchRoleListAction: (params: {
    client_list?: Array<{ name?: string | null }>;
  }) => Promise<Array<{
    id: number;
    name: string;
    is_build_in?: boolean;
    children: Array<{ id: number; name: string }>;
  }>>;
  updateGroupAction: (params: {
    group_id: string | number;
    group_name: string;
    role_ids: number[];
    allow_inherit_roles: boolean;
  }) => Promise<unknown>;
}

interface ModalConfig {
  type: 'edit';
  groupId: string | number;
  groupName?: string;
  roleIds?: number[];
}

export interface GroupModalRef {
  showModal: (config: ModalConfig) => void;
}

const GroupEditModal = forwardRef<GroupModalRef, ModalProps>(({
  onSuccess,
  clientData,
  fetchGroupDetailWithRolesAction,
  fetchRoleListAction,
  updateGroupAction,
}, ref) => {
  const { t } = useTranslation();
  const formRef = useRef<FormInstance>(null);
  const [visible, setVisible] = useState(false);
  const [roleLoading, setRoleLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [currentGroupId, setCurrentGroupId] = useState<string | number>('');
  const [currentGroupName, setCurrentGroupName] = useState<string>('');
  const [roleTreeData, setRoleTreeData] = useState<TreeDataNode[]>([]);
  const [selectedRoleIds, setSelectedRoleIds] = useState<number[]>([]);
  const [inheritedRoleIds, setInheritedRoleIds] = useState<number[]>([]);
  const [inheritedRoleSourceMap, setInheritedRoleSourceMap] = useState<Record<string, string>>({});
  const [allowInheritRoles, setAllowInheritRoles] = useState(false);

  useEffect(() => {
    if (visible && formRef.current) {
      setTimeout(() => {
        formRef.current?.setFieldsValue({
          groupName: currentGroupName,
          roleIds: selectedRoleIds,
          allowInheritRoles,
        });
      }, 0);
    }
  }, [visible, currentGroupName, selectedRoleIds, allowInheritRoles]);

  const fetchAvailableRoles = async () => {
    try {
      setRoleLoading(true);
      const roleData = await fetchRoleListAction({ client_list: clientData });
      setRoleTreeData(processRoleTreeData(roleData, t('common.externalApp')));
    } catch (error) {
      console.error('Failed to fetch roles:', error);
      message.error(t('common.fetchFailed'));
    } finally {
      setRoleLoading(false);
    }
  };

  const fetchGroupDetail = async (groupId: string | number) => {
    try {
      const detail = await fetchGroupDetailWithRolesAction({ group_id: groupId });
      setInheritedRoleIds(detail.inherited_role_ids || []);
      setInheritedRoleSourceMap(detail.inherited_role_source_map || {});
      setSelectedRoleIds(detail.own_role_ids || []);
      setAllowInheritRoles(detail.allow_inherit_roles ?? false);
      formRef.current?.setFieldsValue({
        allowInheritRoles: detail.allow_inherit_roles ?? false,
        roleIds: detail.own_role_ids || [],
      });
    } catch (error) {
      console.error('Failed to fetch group detail:', error);
    }
  };

  useImperativeHandle(ref, () => ({
    showModal: ({ type, groupId, groupName }) => {
      setVisible(true);
      setCurrentGroupId(groupId);
      setCurrentGroupName(groupName || '');
      setAllowInheritRoles(false);
      formRef.current?.resetFields();

      if (type === 'edit') {
        fetchGroupDetail(groupId);
        fetchAvailableRoles();
      }
    },
  }));

  const handleCancel = () => {
    setVisible(false);
    setSelectedRoleIds([]);
    setInheritedRoleIds([]);
    setInheritedRoleSourceMap({});
  };

  const handleConfirm = async () => {
    try {
      setIsSubmitting(true);
      const formData = await formRef.current?.validateFields();

      await updateGroupAction({
        group_id: currentGroupId,
        group_name: formData.groupName,
        role_ids: formData.roleIds || [],
        allow_inherit_roles: formData.allowInheritRoles ?? false,
      });

      message.success(t('common.updateSuccess'));
      onSuccess();
      setVisible(false);
    } catch (error: any) {
      if (error.errorFields && error.errorFields.length) {
        const firstFieldErrorMessage = error.errorFields[0].errors[0];
        message.error(firstFieldErrorMessage || t('common.valFailed'));
      } else {
        message.error(t('common.saveFailed'));
      }
      console.error('Failed to update group:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRoleChange = (newKeys: number[]) => {
    setSelectedRoleIds(newKeys);
    formRef.current?.setFieldsValue({ roleIds: newKeys });
  };

  const handleAllowInheritRolesChange = (checked: boolean) => {
    setAllowInheritRoles(checked);
    formRef.current?.setFieldsValue({ allowInheritRoles: checked });
  };

  return (
    <OperateFormModal
      title={t('system.group.editGroup')}
      width={860}
      open={visible}
      onCancel={handleCancel}
      confirmText={t('common.confirm')}
      cancelText={t('common.cancel')}
      onConfirm={handleConfirm}
      confirmLoading={isSubmitting}
      cancelDisabled={isSubmitting}
      primaryFirst={false}
    >
      <Form ref={formRef} layout="vertical">
        <Form.Item
          name="groupName"
          label={t('system.group.form.name')}
          rules={[{ required: true, message: t('common.inputRequired') }]}
          className="mb-0"
        >
          <Input
            placeholder={`${t('common.inputMsg')}${t('system.group.form.name')}`}
          />
        </Form.Item>

        <div className="mt-4 flex items-center justify-between">
          <div className="flex items-center gap-1 text-[14px] font-medium text-(--color-text-1)">
            <span>{t('system.group.organizationRoles')}</span>
            <Tooltip title={t('system.group.organizationRolesTooltip')}>
              <InfoCircleOutlined className="text-(--color-text-3)" />
            </Tooltip>
          </div>
          <div className="flex items-center gap-3">
            <Form.Item
              name="allowInheritRoles"
              valuePropName="checked"
              className="mb-0"
            >
              <Switch size="small" onChange={handleAllowInheritRolesChange} />
            </Form.Item>
            <span className="text-[14px] text-(--color-text-2)">{t('system.group.allowInheritRoles')}</span>
          </div>
        </div>

        <Form.Item
          name="roleIds"
          className="mt-3"
        >
          <RoleTransfer
            treeData={roleTreeData}
            selectedKeys={selectedRoleIds}
            loading={roleLoading}
            onChange={handleRoleChange}
            groupRules={{}}
            forceOrganizationRole={true}
            inheritedRoleIds={inheritedRoleIds}
            inheritedRoleSourceMap={inheritedRoleSourceMap}
          />
        </Form.Item>
      </Form>
    </OperateFormModal>
  );
});

GroupEditModal.displayName = 'GroupEditModal';
export default GroupEditModal;
export { processRoleTreeData } from './role-tree-utils';
export type { RoleTreeItem } from './role-tree-utils';
