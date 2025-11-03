import React, { useState, useRef, forwardRef, useImperativeHandle, useEffect } from 'react';
import { Input, Button, Form, message } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useGroupApi } from '@/app/system-manager/api/group';
import { useUserApi } from '@/app/system-manager/api/user';
import { useClientData } from '@/context/client';
import RoleTransfer from '@/app/system-manager/components/user/roleTransfer';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';

interface ModalProps {
  onSuccess: () => void;
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

const GroupEditModal = forwardRef<GroupModalRef, ModalProps>(({ onSuccess }, ref) => {
  const { t } = useTranslation();
  const { clientData } = useClientData();
  const formRef = useRef<FormInstance>(null);
  const [visible, setVisible] = useState(false);
  const [roleLoading, setRoleLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [currentGroupId, setCurrentGroupId] = useState<string | number>('');
  const [currentGroupName, setCurrentGroupName] = useState<string>('');
  const [roleTreeData, setRoleTreeData] = useState<TreeDataNode[]>([]);
  const [selectedRoleIds, setSelectedRoleIds] = useState<number[]>([]);

  const { updateGroup } = useGroupApi();
  const { getRoleList } = useUserApi();

  // 确保在表单渲染完成后设置字段值
  useEffect(() => {
    if (visible && formRef.current) {
      // 使用 setTimeout 确保表单完全渲染
      setTimeout(() => {
        formRef.current?.setFieldsValue({
          groupName: currentGroupName,
          roleIds: selectedRoleIds,
        });
      }, 0);
    }
  }, [visible, currentGroupName, selectedRoleIds]);

  // 获取可用的角色列表
  const fetchAvailableRoles = async () => {
    try {
      setRoleLoading(true);
      const roleData = await getRoleList({ client_list: clientData });

      // 转换为Transfer组件需要的树形数据格式
      const formattedRoles = roleData.map((item: any) => ({
        key: item.id,
        title: item.name,
        selectable: false,
        children: item.children.map((child: any) => ({
          key: child.id,
          title: child.name,
          selectable: true,
        })),
      }));

      setRoleTreeData(formattedRoles);
    } catch (error) {
      console.error('Failed to fetch roles:', error);
      message.error(t('common.fetchFailed'));
    } finally {
      setRoleLoading(false);
    }
  };

  useImperativeHandle(ref, () => ({
    showModal: ({ type, groupId, groupName, roleIds }) => {
      setVisible(true);
      setCurrentGroupId(groupId);
      setCurrentGroupName(groupName || '');
      formRef.current?.resetFields();

      if (type === 'edit') {
        const currentRoleIds = roleIds || [];
        setSelectedRoleIds(currentRoleIds);

        fetchAvailableRoles();
      }
    },
  }));

  const handleCancel = () => {
    setVisible(false);
    setSelectedRoleIds([]);
  };

  const handleConfirm = async () => {
    try {
      setIsSubmitting(true);
      const formData = await formRef.current?.validateFields();

      await updateGroup({
        group_id: currentGroupId,
        group_name: formData.groupName,
        role_ids: formData.roleIds || [],
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

  return (
    <OperateModal
      title={t('system.group.editGroup')}
      width={860}
      open={visible}
      onCancel={handleCancel}
      footer={[
        <Button key="cancel" onClick={handleCancel} disabled={isSubmitting}>
          {t('common.cancel')}
        </Button>,
        <Button key="submit" type="primary" onClick={handleConfirm} loading={isSubmitting}>
          {t('common.confirm')}
        </Button>,
      ]}
    >
      <Form ref={formRef} layout="vertical">
        <Form.Item
          name="groupName"
          label={t('system.group.form.name')}
          rules={[{ required: true, message: t('common.inputRequired') }]}
        >
          <Input
            placeholder={`${t('common.inputMsg')}${t('system.group.form.name')}`}
          />
        </Form.Item>

        <Form.Item
          name="roleIds"
          label={t('system.group.organizationRoles')}
          tooltip={t('system.group.organizationRolesTooltip')}
        >
          <RoleTransfer
            treeData={roleTreeData}
            selectedKeys={selectedRoleIds}
            loading={roleLoading}
            onChange={handleRoleChange}
            groupRules={{}}
            forceOrganizationRole={true}
          />
        </Form.Item>
      </Form>
    </OperateModal>
  );
});

GroupEditModal.displayName = 'GroupEditModal';
export default GroupEditModal;
