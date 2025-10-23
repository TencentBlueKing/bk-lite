import React, { useState, useRef, forwardRef, useImperativeHandle } from 'react';
import { Input, Button, Form, message, Spin, Select } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useUserApi } from '@/app/system-manager/api/user/index';
import { useGroupApi } from '@/app/system-manager/api/group/index';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { useClientData } from '@/context/client';
import { ZONEINFO_OPTIONS, LOCALE_OPTIONS } from '@/app/system-manager/constants/userDropdowns';
import RoleTransfer from '@/app/system-manager/components/user/roleTransfer';

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

// 组织角色接口定义
interface GroupRole {
  id: number;
  name: string;
  app: string;
}

const UserModal = forwardRef<ModalRef, ModalProps>(({ onSuccess, treeData }, ref) => {
  const { t } = useTranslation();
  const formRef = useRef<FormInstance>(null);
  const { clientData } = useClientData();
  const [currentUserId, setCurrentUserId] = useState('');
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [roleLoading, setRoleLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [type, setType] = useState<'add' | 'edit'>('add');
  const [roleTreeData, setRoleTreeData] = useState<TreeDataNode[]>([]);
  const [selectedGroups, setSelectedGroups] = useState<number[]>([]);
  const [selectedRoles, setSelectedRoles] = useState<number[]>([]);
  const [groupRules, setGroupRules] = useState<{ [key: string]: { [app: string]: number } }>({});
  const [organizationRoleIds, setOrganizationRoleIds] = useState<number[]>([]);

  const { addUser, editUser, getUserDetail, getRoleList } = useUserApi();
  const { getGroupRoles } = useGroupApi();

  // 获取组织角色 - 修改为返回数据
  const fetchGroupRoles = async (groupIds: number[]): Promise<GroupRole[]> => {
    if (groupIds.length === 0) {
      setOrganizationRoleIds([]);
      return [];
    }

    try {
      const groupRoleData = await getGroupRoles({ group_ids: groupIds });

      // 提取组织角色的ID列表
      const orgRoleIds = (groupRoleData || []).map((role: GroupRole) => role.id);
      setOrganizationRoleIds(orgRoleIds);

      return groupRoleData || [];
    } catch (error) {
      console.error('Failed to fetch group roles:', error);
      setOrganizationRoleIds([]);
      return [];
    }
  };

  // 修改角色树数据，禁用组织角色
  const processRoleTreeData = (roleData: any[], orgRoleIds: number[]): TreeDataNode[] => {
    return roleData.map((item: any) => ({
      key: item.id,
      title: item.name,
      selectable: false,
      children: item.children.map((child: any) => ({
        key: child.id,
        title: child.name,
        selectable: true,
        disabled: orgRoleIds.includes(child.id), // 禁用组织角色
      })),
    }));
  };

  const fetchRoleInfo = async () => {
    try {
      setRoleLoading(true);
      const roleData = await getRoleList({ client_list: clientData });

      // 根据是否有组织角色来处理角色树数据
      const processedRoleData = processRoleTreeData(roleData, organizationRoleIds);
      setRoleTreeData(processedRoleData);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setRoleLoading(false);
    }
  };

  const fetchUserDetail = async (userId: string) => {
    setLoading(true);
    try {
      const id = clientData.map(client => client.id);
      const userDetail = await getUserDetail({ user_id: userId, id });
      if (userDetail) {
        setCurrentUserId(userId);
        const userGroupIds = userDetail.groups?.map((group: { id: number }) => group.id) || [];

        // 先设置用户的分组信息
        setSelectedGroups(userGroupIds);

        // 用户详情中的 roles 就是个人角色
        const personalRoles = userDetail.roles?.map((role: { role_id: number }) => role.role_id) || [];

        // 获取组织角色信息
        const groupRoleData = await fetchGroupRoles(userGroupIds);

        // 等待组织角色获取完成后，合并个人角色和组织角色
        const orgRoleIds = (groupRoleData || []).map((role: GroupRole) => role.id);
        const allRoles = [...personalRoles, ...orgRoleIds];

        setSelectedRoles(allRoles);

        formRef.current?.setFieldsValue({
          ...userDetail,
          lastName: userDetail?.display_name,
          zoneinfo: userDetail?.timezone,
          roles: allRoles, // 设置合并后的所有角色
          groups: userGroupIds,
        });

        const groupRulesObj = userDetail.groups?.reduce((acc: { [key: string]: { [app: string]: number } }, group: {id: number; rules: { [key: string]: number } }) => {
          acc[group.id] = group.rules || {};
          return acc;
        }, {});
        setGroupRules(groupRulesObj || {});
      }
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useImperativeHandle(ref, () => ({
    showModal: ({ type, userId, groupKeys = [] }) => {
      setVisible(true);
      setType(type);
      formRef.current?.resetFields();

      // 重置状态
      setOrganizationRoleIds([]);

      if (type === 'edit' && userId) {
        fetchUserDetail(userId);
      } else if (type === 'add') {
        setSelectedGroups(groupKeys);
        setSelectedRoles([]);

        // 新增用户时也需要获取组织角色
        if (groupKeys.length > 0) {
          fetchGroupRoles(groupKeys);
        }

        setTimeout(() => {
          formRef.current?.setFieldsValue({ groups: groupKeys, zoneinfo: "Asia/Shanghai", locale: "en" });
        }, 0);
      }

      // 延迟获取角色信息，确保组织角色已加载
      setTimeout(() => {
        fetchRoleInfo();
      }, 100);
    },
  }));

  const handleCancel = () => {
    setVisible(false);
  };

  const handleConfirm = async () => {
    try {
      setIsSubmitting(true);
      const formData = await formRef.current?.validateFields();
      const { zoneinfo, ...restData } = formData;

      // 分离个人角色和组织角色
      const personalRoles = (formData.roles || []).filter((roleId: number) => !organizationRoleIds.includes(roleId));

      // 修复 rules 数据处理逻辑，将 groupRules 转换为正确的格式
      const rules = Object.values(groupRules)
        .filter(group => group && typeof group === 'object' && Object.keys(group).length > 0)
        .flatMap(group => Object.values(group))
        .filter(rule => typeof rule === 'number');

      const payload = {
        ...restData,
        roles: personalRoles, // 只提交个人角色
        rules,
        timezone: zoneinfo,
      };

      if (type === 'add') {
        await addUser(payload);
        message.success(t('common.addSuccess'));
      } else {
        await editUser({ user_id: currentUserId, ...payload });
        message.success(t('common.updateSuccess'));
      }
      onSuccess();
      setVisible(false);
    } catch (error: any) {
      if (error.errorFields && error.errorFields.length) {
        const firstFieldErrorMessage = error.errorFields[0].errors[0];
        message.error(firstFieldErrorMessage || t('common.valFailed'));
      } else {
        message.error(t('common.saveFailed'));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const transformTreeData = (data: any) => {
    return data.map((node: any) => ({
      title: node.title || 'Unknown',
      value: node.key as number,
      key: node.key as number,
      children: node.children ? transformTreeData(node.children) : []
    }));
  };

  const filteredTreeData = treeData ? transformTreeData(treeData) : [];

  const handleChangeRule = (newKey: number, newRules: { [app: string]: number }) => {
    setGroupRules({
      ...groupRules,
      [newKey]: newRules
    });
  };

  // 处理分组变化，重新获取组织角色
  const handleGroupChange = async (newGroupIds: number[]) => {
    setSelectedGroups(newGroupIds);
    formRef.current?.setFieldsValue({ groups: newGroupIds });

    // 当分组变化时，重新获取组织角色
    const newGroupRoleData = await fetchGroupRoles(newGroupIds);
    const newOrgRoleIds = newGroupRoleData.map(role => role.id);

    // 更新角色选择：移除旧的组织角色，保留个人角色，添加新的组织角色
    const currentPersonalRoles = selectedRoles.filter(roleId => !organizationRoleIds.includes(roleId));
    const updatedRoles = [...currentPersonalRoles, ...newOrgRoleIds];

    setSelectedRoles(updatedRoles);
    formRef.current?.setFieldsValue({ roles: updatedRoles });

    // 重新获取角色信息以更新禁用状态
    setTimeout(() => {
      fetchRoleInfo();
    }, 100);
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
        <Button key="submit" type="primary" onClick={handleConfirm} loading={isSubmitting || loading}>
          {t('common.confirm')}
        </Button>,
      ]}
    >
      <Spin spinning={loading}>
        <Form ref={formRef} layout="vertical">
          {/* ...existing form fields... */}
          <Form.Item
            name="username"
            label={t('system.user.form.username')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <Input placeholder={`${t('common.inputMsg')}${t('system.user.form.username')}`} disabled={type === 'edit'} />
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
            <Select showSearch placeholder={`${t('common.selectMsg')}${t('system.user.form.zoneinfo')}`}>
              {ZONEINFO_OPTIONS.map(option => (
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
              {LOCALE_OPTIONS.map(option => (
                <Select.Option key={option.value} value={option.value}>
                  {t(option.label)}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            name="groups"
            label={t('system.user.form.group')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
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
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <RoleTransfer
              groupRules={groupRules}
              treeData={roleTreeData}
              selectedKeys={selectedRoles}
              loading={roleLoading}
              forceOrganizationRole={false}
              organizationRoleIds={organizationRoleIds}
              onChange={newKeys => {
                setSelectedRoles(newKeys);
                formRef.current?.setFieldsValue({ roles: newKeys });
              }}
            />
          </Form.Item>
        </Form>
      </Spin>
    </OperateModal>
  );
});

UserModal.displayName = 'UserModal';
export default UserModal;
