import React, { useState, useRef, forwardRef, useImperativeHandle } from 'react';
import { Input, Button, Form, message, Spin, Select, Radio, Alert } from 'antd';
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
  const [isSuperuser, setIsSuperuser] = useState<boolean>(false);

  const { addUser, editUser, getUserDetail, getRoleList } = useUserApi();
  const { getGroupRoles } = useGroupApi();

  const fetchGroupRoles = async (groupIds: number[]): Promise<GroupRole[]> => {
    if (groupIds.length === 0) {
      setOrganizationRoleIds([]);
      return [];
    }

    try {
      const groupRoleData = await getGroupRoles({ group_ids: groupIds });

      const orgRoleIds = (groupRoleData || []).map((role: GroupRole) => role.id);
      setOrganizationRoleIds(orgRoleIds);
      
      await fetchRoleInfoWithOrgRoles(orgRoleIds);

      return groupRoleData || [];
    } catch (error) {
      console.error('Failed to fetch group roles:', error);
      setOrganizationRoleIds([]);
      return [];
    }
  };

  const fetchRoleInfoWithOrgRoles = async (orgRoleIds: number[]) => {
    try {
      setRoleLoading(true);
      const roleData = await getRoleList({ client_list: clientData });

      const processedRoleData = processRoleTreeData(roleData, orgRoleIds);
      setRoleTreeData(processedRoleData);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setRoleLoading(false);
    }
  };

  const processRoleTreeData = (roleData: any[], orgRoleIds: number[]): TreeDataNode[] => {
    return roleData.map((item: any) => ({
      key: item.id,
      title: item.name,
      selectable: false,
      children: item.children.map((child: any) => ({
        key: child.id,
        title: child.name,
        selectable: true,
        disabled: orgRoleIds.includes(child.id),
      })),
    }));
  };

  const fetchRoleInfo = async () => {
    await fetchRoleInfoWithOrgRoles(organizationRoleIds);
  };

  const fetchUserDetail = async (userId: string) => {
    setLoading(true);
    try {
      const id = clientData.map(client => client.id);
      const userDetail = await getUserDetail({ user_id: userId, id });
      if (userDetail) {
        setCurrentUserId(userId);
        const userGroupIds = userDetail.groups?.map((group: { id: number }) => group.id) || [];

        setSelectedGroups(userGroupIds);
        const personalRoles = userDetail.roles?.map((role: { role_id: number }) => role.role_id) || [];
        const groupRoleData = await fetchGroupRoles(userGroupIds);
        const orgRoleIds = (groupRoleData || []).map((role: GroupRole) => role.id);
        const allRoles = [...personalRoles, ...orgRoleIds];

        setSelectedRoles(allRoles);

        setIsSuperuser(userDetail?.is_superuser || false);

        formRef.current?.setFieldsValue({
          ...userDetail,
          lastName: userDetail?.display_name,
          zoneinfo: userDetail?.timezone,
          roles: allRoles,
          groups: userGroupIds,
          is_superuser: userDetail?.is_superuser || false,
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
      setIsSuperuser(false);

      if (type === 'edit' && userId) {
        setOrganizationRoleIds([]);
        fetchUserDetail(userId);
        setTimeout(() => {
          fetchRoleInfo();
        }, 100);
      } else if (type === 'add') {
        setOrganizationRoleIds([]);
        setSelectedGroups(groupKeys);
        setSelectedRoles([]);

        if (groupKeys.length > 0) {
          fetchGroupRoles(groupKeys);
        } else {
          fetchRoleInfoWithOrgRoles([]);
        }

        setTimeout(() => {
          formRef.current?.setFieldsValue({ groups: groupKeys, zoneinfo: "Asia/Shanghai", locale: "en", is_superuser: false });
        }, 0);
      }
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

      let payload;
      
      if (formData.is_superuser) {
        payload = {
          ...restData,
          roles: [],
          timezone: zoneinfo,
          is_superuser: true,
        };
      } else {
        const personalRoles = (formData.roles || []).filter((roleId: number) => !organizationRoleIds.includes(roleId));

        const rules = Object.values(groupRules)
          .filter(group => group && typeof group === 'object' && Object.keys(group).length > 0)
          .flatMap(group => Object.values(group))
          .filter(rule => typeof rule === 'number');

        payload = {
          ...restData,
          roles: personalRoles,
          rules,
          timezone: zoneinfo,
          is_superuser: false,
        };
      }

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

  const handleGroupChange = async (newGroupIds: number[]) => {
    setSelectedGroups(newGroupIds);
    formRef.current?.setFieldsValue({ groups: newGroupIds });

    // fetchGroupRoles 会自动更新 organizationRoleIds 和角色树
    const newGroupRoleData = await fetchGroupRoles(newGroupIds);
    const newOrgRoleIds = newGroupRoleData.map(role => role.id);

    // 使用新的组织角色 ID 来过滤个人角色
    const currentPersonalRoles = selectedRoles.filter(roleId => !newOrgRoleIds.includes(roleId));
    const updatedRoles = [...currentPersonalRoles, ...newOrgRoleIds];

    setSelectedRoles(updatedRoles);
    formRef.current?.setFieldsValue({ roles: updatedRoles });
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
            <Form.Item
              name="is_superuser"
              style={{ marginBottom: 8 }}
            >
              <Radio.Group 
                onChange={(e) => {
                  const value = e.target.value;
                  setIsSuperuser(value);
                  formRef.current?.setFieldsValue({ is_superuser: value });
                }}
              >
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
                onChange={newKeys => {
                  setSelectedRoles(newKeys);
                  formRef.current?.setFieldsValue({ roles: newKeys });
                }}
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
