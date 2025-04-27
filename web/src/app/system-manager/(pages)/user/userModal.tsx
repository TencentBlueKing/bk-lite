import React, { useState, useRef, forwardRef, useImperativeHandle } from 'react';
import { Input, Button, Form, message, Spin, Select } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useUserApi } from '@/app/system-manager/api/user/index';
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
  groupKeys?: string[];
}

export interface ModalRef {
  showModal: (config: ModalConfig) => void;
}

const UserModal = forwardRef<ModalRef, ModalProps>(({ onSuccess, treeData }, ref) => {
  const { t } = useTranslation();
  const formRef = useRef<FormInstance>(null);
  const { clientData } = useClientData();
  const [currentUserId, setCurrentUserId] = useState('');
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [type, setType] = useState<'add' | 'edit'>('add');
  const [roleTreeData, setRoleTreeData] = useState<TreeDataNode[]>([]);
  const [selectedGroups, setSelectedGroups] = useState<string[]>([]);
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [roleMaps, setRoleMaps] = useState<{ [key: string]: string }>({});
  const [groupRules, setGroupRules] = useState<{ [key: string]: number[] }>({});

  const { addUser, editUser, getUserDetail, getRoleList } = useUserApi();

  const fetchRoleInfo = async () => {
    try {
      const roleData = await getRoleList({ client_list: clientData });
      const mapping: { [key: string]: string } = {};
      roleData.forEach((item: any) => {
        item.children && item.children.forEach((child: any) => {
          mapping[String(child.role_id)] = child.role_name;
        });
      });
      setRoleMaps(mapping);
      setRoleTreeData(
        roleData.map((item: any) => ({
          key: String(item.id),
          title: item.display_name,
          selectable: false,
          children: item.children.map((child: any) => ({
            key: String(child.role_id),
            title: child.display_name,
            selectable: true,
          })),
        }))
      );
    } catch {
      message.error(t('common.fetchFailed'));
    }
  };

  const fetchUserDetail = async (userId: string) => {
    setLoading(true);
    try {
      const id = clientData.map(client => client.id);
      const userDetail = await getUserDetail({ user_id: userId, id });
      if (userDetail) {
        setCurrentUserId(userId);
        formRef.current?.setFieldsValue({
          ...userDetail,
          roles: userDetail.roles?.map((role: { role_id: string }) => role.role_id) || [],
          groups: userDetail.groups?.map((group: { id: string }) => group.id) || [],
          zoneinfo: userDetail.attributes?.zoneinfo ? userDetail.attributes.zoneinfo[0] : undefined,
          locale: userDetail.attributes?.locale ? userDetail.attributes.locale[0] : undefined,
        });
        setSelectedRoles(userDetail.roles?.map((role: { role_id: string }) => role.role_id) || []);
        setSelectedGroups(userDetail.groups?.map((group: { id: string }) => group.id) || []);

        const groupRulesObj = userDetail.groups?.reduce((acc: { [key: string]: number[] }, group: { id: string; rules: { [key: string]: number } }) => {
          acc[group.id] = Object.values(group.rules) || [];
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
      if (type === 'edit' && userId) {
        fetchUserDetail(userId);
      } else if (type === 'add') {
        setSelectedGroups(groupKeys);
        setSelectedRoles([]);
        setTimeout(() => {
          formRef.current?.setFieldsValue({ groups: groupKeys, zoneinfo: "Asia/Shanghai", locale: "en" });
        }, 0);
      }
      fetchRoleInfo();
    },
  }));

  const handleCancel = () => {
    setVisible(false);
  };

  const handleConfirm = async () => {
    try {
      setIsSubmitting(true);
      const formData = await formRef.current?.validateFields();
      const { zoneinfo, locale, ...restData } = formData;
      const roles: { id: string; name: string }[] = [];
      roleTreeData.forEach(parent => {
        if (parent.children) {
          parent.children.forEach((child: any) => {
            if (selectedRoles.includes(child.key)) {
              roles.push({ id: child.key as string, name: roleMaps[child.key] });
            }
          });
        }
      });
      const payload = {
        ...restData,
        roles,
        rules: Object.values(groupRules).flat(2),
        attributes: { zoneinfo: [zoneinfo], locale: [locale] }
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
      value: node.key,
      key: node.key,
      children: node.children ? transformTreeData(node.children) : []
    }));
  };

  const filteredTreeData = treeData ? transformTreeData(treeData) : [];

  const handleChangeRule = (newKey: string, newRules: number[]) => {
    setGroupRules({
      ...groupRules,
      [newKey]: newRules
    });
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
              groupRules={groupRules}
              treeData={filteredTreeData}
              selectedKeys={selectedGroups}
              onChange={newKeys => {
                setSelectedGroups(newKeys);
                formRef.current?.setFieldsValue({ groups: newKeys });
              }}
              onChangeRule={handleChangeRule}
            />
          </Form.Item>
          <Form.Item
            name="roles"
            label={t('system.user.form.role')}
            rules={[{ required: true, message: t('common.inputRequired') }]}
          >
            <RoleTransfer
              groupRules={groupRules}
              treeData={roleTreeData}
              selectedKeys={selectedRoles}
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
