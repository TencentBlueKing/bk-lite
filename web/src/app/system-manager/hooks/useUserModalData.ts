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
  type GroupRules,
  type TreeSelectNode,
  type UserDetailResponse,
  processRoleTreeData,
  extractGroupIds,
  extractPersonalRoleIds,
  buildGroupRulesFromUserDetail,
  buildFormValuesFromUserDetail,
  buildUserPayload,
  hasNormalGroupSelection,
  mergeRoles,
} from '@/app/system-manager/utils/userFormUtils';

interface ModalConfig {
  type: 'add' | 'edit';
  userId?: string;
  groupKeys?: React.Key[];
  groupTreeData?: TreeSelectNode[];
}

interface UseUserModalDataReturn {
  formRef: React.RefObject<FormInstance | null>;
  visible: boolean;
  loading: boolean;
  roleLoading: boolean;
  isSubmitting: boolean;
  type: 'add' | 'edit';
  roleTreeData: TreeDataNode[];
  selectedGroups: React.Key[];
  selectedRoles: number[];
  personalRoleIds: number[];
  groupRules: GroupRules;
  organizationRoleIds: number[];
  organizationRoleSourceMap: Record<string, string>;
  isSuperuser: boolean;
  currentUserId: string;
  setSelectedGroups: (groups: React.Key[]) => void;
  setSelectedRoles: (roles: number[]) => void;
  handleRoleChange: (newRoleIds: React.Key[]) => void;
  handleSuperuserChange: (value: boolean) => void;
  setGroupRules: (rules: GroupRules) => void;
  setIsSuperuser: (value: boolean) => void;
  showModal: (config: ModalConfig) => void;
  handleCancel: () => void;
  handleConfirm: (onSuccess: () => void) => Promise<void>;
  handleGroupChange: (newGroupIds: React.Key[]) => Promise<void>;
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
  const [selectedGroups, setSelectedGroups] = useState<React.Key[]>([]);
  const [selectedRoles, setSelectedRoles] = useState<number[]>([]);
  const [personalRoleIds, setPersonalRoleIds] = useState<number[]>([]);
  const [groupRules, setGroupRules] = useState<GroupRules>({});
  const [organizationRoleIds, setOrganizationRoleIds] = useState<number[]>([]);
  const [organizationRoleSourceMap, setOrganizationRoleSourceMap] = useState<Record<string, string>>({});
  const [isSuperuser, setIsSuperuser] = useState<boolean>(false);
  const [groupTreeData, setGroupTreeData] = useState<TreeSelectNode[]>([]);

  const { addUser, editUser, getUserDetail, getRoleList } = useUserApi();
  const { getGroupDetailWithRoles } = useGroupApi();

  const fetchRoleInfoWithOrgRoles = useCallback(
    async () => {
      try {
        setRoleLoading(true);
        const roleData = await getRoleList({ client_list: clientData });
        const processedRoleData = processRoleTreeData(roleData);
        setRoleTreeData(processedRoleData);
      } catch {
        message.error(t('common.fetchFailed'));
      } finally {
        setRoleLoading(false);
      }
    },
    [getRoleList, clientData, t]
  );

  const fetchOrganizationRoleIds = useCallback(
    async (groupIds: React.Key[]): Promise<number[]> => {
      if (groupIds.length === 0) {
        setOrganizationRoleIds([]);
        setOrganizationRoleSourceMap({});
        return [];
      }

      try {
        const groupDetails = await Promise.all(
          groupIds.map((groupId) => getGroupDetailWithRoles({ group_id: String(groupId) }))
        );

        const orgRoleSourceMap = groupDetails.reduce<Record<string, string>>((acc, detail) => {
          [...(detail.own_role_ids || []), ...(detail.inherited_role_ids || [])].forEach((roleId) => {
            const roleKey = String(roleId);
            const existingGroupNames = acc[roleKey] ? acc[roleKey].split(', ') : [];

            if (!existingGroupNames.includes(detail.group_name)) {
              acc[roleKey] = [...existingGroupNames, detail.group_name].filter(Boolean).join(', ');
            }
          });

          return acc;
        }, {});

        const orgRoleIds = [...new Set(
          groupDetails.flatMap((detail) => [
            ...(detail.own_role_ids || []),
            ...(detail.inherited_role_ids || []),
          ])
        )];

        setOrganizationRoleIds(orgRoleIds);
        setOrganizationRoleSourceMap(orgRoleSourceMap);
        await fetchRoleInfoWithOrgRoles();
        return orgRoleIds;
      } catch (error) {
        console.error('Failed to fetch group roles:', error);
        setOrganizationRoleIds([]);
        setOrganizationRoleSourceMap({});
        return [];
      }
    },
    [getGroupDetailWithRoles, fetchRoleInfoWithOrgRoles]
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
          const orgRoleIds = await fetchOrganizationRoleIds(userGroupIds);
          const allRoles = mergeRoles(personalRoles, orgRoleIds);

          setPersonalRoleIds(personalRoles);
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
    [clientData, getUserDetail, fetchOrganizationRoleIds, t]
  );

  const showModal = useCallback(
    ({ type: modalType, userId, groupKeys = [], groupTreeData: nextGroupTreeData = [] }: ModalConfig) => {
      setVisible(true);
      setType(modalType);
      setGroupTreeData(nextGroupTreeData);
      formRef.current?.resetFields();
      setIsSuperuser(false);

      if (modalType === 'edit' && userId) {
        setOrganizationRoleIds([]);
        setOrganizationRoleSourceMap({});
        fetchUserDetail(userId);
      } else if (modalType === 'add') {
        setOrganizationRoleIds([]);
        setOrganizationRoleSourceMap({});
        setSelectedGroups(groupKeys);
        setPersonalRoleIds([]);
        setSelectedRoles([]);
        setGroupRules({});

        if (groupKeys.length > 0) {
          void fetchOrganizationRoleIds(groupKeys).then((orgRoleIds) => {
            const mergedRoleIds = mergeRoles([], orgRoleIds);
            setSelectedRoles(mergedRoleIds);
            formRef.current?.setFieldsValue({ roles: mergedRoleIds });
          });
        } else {
          fetchRoleInfoWithOrgRoles();
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
    [fetchUserDetail, fetchOrganizationRoleIds, fetchRoleInfoWithOrgRoles]
  );

  const handleCancel = useCallback(() => {
    setVisible(false);
  }, []);

  const handleConfirm = useCallback(
    async (onSuccess: () => void) => {
      try {
        setIsSubmitting(true);
        const formData = await formRef.current?.validateFields();

        if (!isSuperuser && selectedGroups.length === 0) {
          message.error(t('system.user.form.groupSelectionRequired'));
          return;
        }

        if (!isSuperuser && !hasNormalGroupSelection(selectedGroups, groupTreeData)) {
          message.error(t('system.user.form.normalGroupRequired'));
          return;
        }

        if (!isSuperuser && selectedRoles.length === 0) {
          message.error(t('common.inputRequired'));
          return;
        }

        const payload = buildUserPayload(
          {
            ...formData,
            groups: selectedGroups,
            roles: selectedRoles,
            is_superuser: isSuperuser,
          },
          personalRoleIds,
          groupRules,
          isSuperuser
        );

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
    [personalRoleIds, organizationRoleIds, groupRules, isSuperuser, type, addUser, editUser, currentUserId, selectedGroups, selectedRoles, t]
  );

  const handleRoleChange = useCallback(
    (newRoleIds: React.Key[]) => {
      const nextPersonalRoleIds = newRoleIds.map((roleId) => Number(roleId));
      setPersonalRoleIds(nextPersonalRoleIds);

      const mergedRoleIds = mergeRoles(nextPersonalRoleIds, organizationRoleIds);
      setSelectedRoles(mergedRoleIds);
      formRef.current?.setFieldsValue({ roles: mergedRoleIds });
    },
    [organizationRoleIds]
  );

  const handleSuperuserChange = useCallback(
    (value: boolean) => {
      setIsSuperuser(value);
      setPersonalRoleIds([]);

      const nextSelectedRoles = value ? [] : organizationRoleIds;
      setSelectedRoles(nextSelectedRoles);

      formRef.current?.setFieldsValue({
        is_superuser: value,
        roles: nextSelectedRoles,
      });
    },
    [organizationRoleIds]
  );

  const handleGroupChange = useCallback(
    async (newGroupIds: React.Key[]) => {
      setSelectedGroups(newGroupIds);
      formRef.current?.setFieldsValue({ groups: newGroupIds });

      const newOrgRoleIds = await fetchOrganizationRoleIds(newGroupIds);

      const updatedRoles = mergeRoles(personalRoleIds, newOrgRoleIds);

      setSelectedRoles(updatedRoles);
      formRef.current?.setFieldsValue({ roles: updatedRoles });
    },
    [fetchOrganizationRoleIds, personalRoleIds]
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
    personalRoleIds,
    groupRules,
    organizationRoleIds,
    organizationRoleSourceMap,
    isSuperuser,
    currentUserId,
    setSelectedGroups,
    setSelectedRoles,
    handleRoleChange,
    handleSuperuserChange,
    setGroupRules,
    setIsSuperuser,
    showModal,
    handleCancel,
    handleConfirm,
    handleGroupChange,
    handleChangeRule,
  };
}
