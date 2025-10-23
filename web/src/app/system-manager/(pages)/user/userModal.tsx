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
  groupKeys?: number[];
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
  const [roleLoading, setRoleLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [type, setType] = useState<'add' | 'edit'>('add');
  const [roleTreeData, setRoleTreeData] = useState<TreeDataNode[]>([]);
  const [selectedGroups, setSelectedGroups] = useState<number[]>([]);
  const [selectedRoles, setSelectedRoles] = useState<number[]>([]);
  const [groupRules, setGroupRules] = useState<{ [key: string]: { [app: string]: number } }>({});

  const { addUser, editUser, getUserDetail, getRoleList } = useUserApi();

  const fetchRoleInfo = async () => {
    try {
      setRoleLoading(true);
      const roleData = await getRoleList({ client_list: clientData });
      setRoleTreeData(
        roleData.map((item: any) => ({
          key: item.id,
          title: item.name,
          selectable: false,
          children: item.children.map((child: any) => ({
            key: child.id,
            title: child.name,
            selectable: true,
          })),
        }))
      );
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
        formRef.current?.setFieldsValue({
          ...userDetail,
          lastName: userDetail?.display_name,
          zoneinfo: userDetail?.timezone,
          roles: userDetail.roles?.map((role: { role_id: number }) => role.role_id) || [],
          groups: userDetail.groups?.map((group: { id: number }) => group.id) || [],
        });
        setSelectedRoles(userDetail.roles?.map((role: { role_id: number }) => role.role_id) || []);
        setSelectedGroups(userDetail.groups?.map((group: { id: number }) => group.id) || []);

        const groupRulesObj = userDetail.groups?.reduce((acc: { [key: string]: { [app: string]: number } }, group: { id: number; rules: { [key: string]: number } }) => {
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
      const { zoneinfo, ...restData } = formData;
      
      // 修复 rules 数据处理逻辑，将 groupRules 转换为正确的格式
      const rules = Object.values(groupRules)
        .filter(group => group && typeof group === 'object' && Object.keys(group).length > 0)
        .flatMap(group => Object.values(group))
        .filter(rule => typeof rule === 'number');

      const payload = {
        ...restData,
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
              loading={roleLoading}
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
