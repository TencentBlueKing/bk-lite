'use client';

import { useState, useCallback, useRef } from 'react';
import type { FormInstance } from 'antd';
import { message } from 'antd';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import { useTranslation } from '@/utils/i18n';
import { useUserApi } from '@/app/system-manager/api/user/index';
import { useGroupApi } from '@/app/system-manager/api/group/index';
import { useClientData } from '@/context/client';
import {
  type GroupRole,
  type GroupRules,
  type UserDetailResponse,
  processRoleTreeData,
  extractGroupIds,
  extractPersonalRoleIds,
  extractOrgRoleIds,
  buildGroupRulesFromUserDetail,
  buildFormValuesFromUserDetail,
  buildUserPayload,
  filterPersonalRoles,
  mergeRoles,
} from '@/app/system-manager/utils/userFormUtils';

interface ModalConfig {
  type: 'add' | 'edit';
  userId?: string;
  groupKeys?: number[];
}

interface UseUserModalDataReturn {
  formRef: React.RefObject<FormInstance | null>;
  visible: boolean;
  loading: boolean;
  roleLoading: boolean;
  isSubmitting: boolean;
  type: 'add' | 'edit';
  roleTreeData: TreeDataNode[];
  selectedGroups: number[];
  selectedRoles: number[];
  groupRules: GroupRules;
  organizationRoleIds: number[];
  isSuperuser: boolean;
  currentUserId: string;
  setSelectedGroups: (groups: number[]) => void;
  setSelectedRoles: (roles: number[]) => void;
  setGroupRules: (rules: GroupRules) => void;
  setIsSuperuser: (value: boolean) => void;
  showModal: (config: ModalConfig) => void;
  handleCancel: () => void;
  handleConfirm: (onSuccess: () => void) => Promise<void>;
  handleGroupChange: (newGroupIds: number[]) => Promise<void>;
  handleChangeRule: (newKey: number, newRules: { [app: string]: number }) => void;
}

export function useUserModalData(): UseUserModalDataReturn {
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
  const [groupRules, setGroupRules] = useState<GroupRules>({});
  const [organizationRoleIds, setOrganizationRoleIds] = useState<number[]>([]);
  const [isSuperuser, setIsSuperuser] = useState<boolean>(false);

  const { addUser, editUser, getUserDetail, getRoleList } = useUserApi();
  const { getGroupRoles } = useGroupApi();

  const fetchRoleInfoWithOrgRoles = useCallback(
    async (orgRoleIds: number[]) => {
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
    },
    [getRoleList, clientData, t]
  );

  const fetchGroupRoles = useCallback(
    async (groupIds: number[]): Promise<GroupRole[]> => {
      if (groupIds.length === 0) {
        setOrganizationRoleIds([]);
        return [];
      }

      try {
        const groupRoleData = await getGroupRoles({ group_ids: groupIds });
        const orgRoleIds = extractOrgRoleIds(groupRoleData || []);
        setOrganizationRoleIds(orgRoleIds);
        await fetchRoleInfoWithOrgRoles(orgRoleIds);
        return groupRoleData || [];
      } catch (error) {
        console.error('Failed to fetch group roles:', error);
        setOrganizationRoleIds([]);
        return [];
      }
    },
    [getGroupRoles, fetchRoleInfoWithOrgRoles]
  );

  const fetchUserDetail = useCallback(
    async (userId: string) => {
      setLoading(true);
      try {
        const id = clientData.map((client) => client.id);
        const userDetail: UserDetailResponse = await getUserDetail({ user_id: userId, id });
        if (userDetail) {
          setCurrentUserId(userId);
          const userGroupIds = extractGroupIds(userDetail);
          setSelectedGroups(userGroupIds);

          const personalRoles = extractPersonalRoleIds(userDetail);
          const groupRoleData = await fetchGroupRoles(userGroupIds);
          const orgRoleIds = extractOrgRoleIds(groupRoleData);
          const allRoles = mergeRoles(personalRoles, orgRoleIds);

          setSelectedRoles(allRoles);
          setIsSuperuser(userDetail?.is_superuser || false);

          formRef.current?.setFieldsValue(buildFormValuesFromUserDetail(userDetail, allRoles, userGroupIds));
          setGroupRules(buildGroupRulesFromUserDetail(userDetail));
        }
      } catch {
        message.error(t('common.fetchFailed'));
      } finally {
        setLoading(false);
      }
    },
    [clientData, getUserDetail, fetchGroupRoles, t]
  );

  const showModal = useCallback(
    ({ type: modalType, userId, groupKeys = [] }: ModalConfig) => {
      setVisible(true);
      setType(modalType);
      formRef.current?.resetFields();
      setIsSuperuser(false);

      if (modalType === 'edit' && userId) {
        setOrganizationRoleIds([]);
        fetchUserDetail(userId);
        setTimeout(() => {
          fetchRoleInfoWithOrgRoles(organizationRoleIds);
        }, 100);
      } else if (modalType === 'add') {
        setOrganizationRoleIds([]);
        setSelectedGroups(groupKeys);
        setSelectedRoles([]);

        if (groupKeys.length > 0) {
          fetchGroupRoles(groupKeys);
        } else {
          fetchRoleInfoWithOrgRoles([]);
        }

        setTimeout(() => {
          formRef.current?.setFieldsValue({
            groups: groupKeys,
            zoneinfo: 'Asia/Shanghai',
            locale: 'en',
            is_superuser: false,
          });
        }, 0);
      }
    },
    [fetchUserDetail, fetchGroupRoles, fetchRoleInfoWithOrgRoles, organizationRoleIds]
  );

  const handleCancel = useCallback(() => {
    setVisible(false);
  }, []);

  const handleConfirm = useCallback(
    async (onSuccess: () => void) => {
      try {
        setIsSubmitting(true);
        const formData = await formRef.current?.validateFields();
        const payload = buildUserPayload(formData, organizationRoleIds, groupRules, isSuperuser);

        if (type === 'add') {
          await addUser(payload);
          message.success(t('common.addSuccess'));
        } else {
          await editUser({ user_id: currentUserId, ...payload });
          message.success(t('common.updateSuccess'));
        }
        onSuccess();
        setVisible(false);
      } catch (error: unknown) {
        const err = error as { errorFields?: Array<{ errors: string[] }> };
        if (err.errorFields && err.errorFields.length) {
          const firstFieldErrorMessage = err.errorFields[0].errors[0];
          message.error(firstFieldErrorMessage || t('common.valFailed'));
        } else {
          message.error(t('common.saveFailed'));
        }
      } finally {
        setIsSubmitting(false);
      }
    },
    [organizationRoleIds, groupRules, isSuperuser, type, addUser, editUser, currentUserId, t]
  );

  const handleGroupChange = useCallback(
    async (newGroupIds: number[]) => {
      setSelectedGroups(newGroupIds);
      formRef.current?.setFieldsValue({ groups: newGroupIds });

      const newGroupRoleData = await fetchGroupRoles(newGroupIds);
      const newOrgRoleIds = newGroupRoleData.map((role) => role.id);

      const currentPersonalRoles = filterPersonalRoles(selectedRoles, newOrgRoleIds);
      const updatedRoles = mergeRoles(currentPersonalRoles, newOrgRoleIds);

      setSelectedRoles(updatedRoles);
      formRef.current?.setFieldsValue({ roles: updatedRoles });
    },
    [fetchGroupRoles, selectedRoles]
  );

  const handleChangeRule = useCallback(
    (newKey: number, newRules: { [app: string]: number }) => {
      setGroupRules({
        ...groupRules,
        [newKey]: newRules,
      });
    },
    [groupRules]
  );

  return {
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
    currentUserId,
    setSelectedGroups,
    setSelectedRoles,
    setGroupRules,
    setIsSuperuser,
    showModal,
    handleCancel,
    handleConfirm,
    handleGroupChange,
    handleChangeRule,
  };
}
